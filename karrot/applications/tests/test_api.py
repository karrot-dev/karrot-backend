from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.applications.factories import ApplicationFactory
from karrot.applications.models import ApplicationStatus
from karrot.conversations.models import Conversation
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership, GroupNotificationType
from karrot.tests.utils import (
    ExtractPaginationMixin,
    execute_scheduled_tasks_immediately,
)
from karrot.users.factories import UserFactory, VerifiedUserFactory
from karrot.users.serializers import UserSerializer
from karrot.utils.tests.fake import faker


class TestCreateApplication(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        mail.outbox = []

        # effectively disable throttling
        from karrot.applications.api import ApplicationsPerDayThrottle

        ApplicationsPerDayThrottle.rate = "1000/min"

    def test_apply_for_group(self):
        self.client.force_login(user=self.applicant)
        answers = faker.text()

        # create application
        response = self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": answers,},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        data = response.data
        application_id = data["id"]
        del data["id"]
        created_at = parse(data["created_at"])
        data["created_at"] = created_at
        self.assertEqual(
            data,
            {
                "questions": self.group.application_questions,
                "answers": answers,
                "user": UserSerializer(self.applicant).data,
                "group": self.group.id,
                "status": "pending",
                "created_at": created_at,
                "decided_by": None,
                "decided_at": None,
            },
        )

        # get conversation
        conversation_response = self.client.get(
            "/api/applications/{}/conversation/".format(application_id)
        )
        self.assertEqual(conversation_response.status_code, status.HTTP_200_OK)
        for user_id in (self.applicant.id, self.member.id):
            self.assertIn(user_id, conversation_response.data["participants"])
        conversation_id = conversation_response.data["id"]
        message_response = self.get_results(
            "/api/messages/?conversation={}".format(conversation_id)
        )
        self.assertEqual(len(message_response.data), 0)

        # list application
        application_list_response = self.get_results("/api/applications/")
        self.assertEqual(application_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(application_list_response.data), 1)
        data = application_list_response.data[0]
        data["created_at"] = parse(data["created_at"])
        self.assertEqual(
            data,
            {
                "id": application_id,
                "questions": self.group.application_questions,
                "answers": answers,
                "user": UserSerializer(self.applicant).data,
                "group": self.group.id,
                "status": "pending",
                "created_at": created_at,
                "decided_by": None,
                "decided_at": None,
            },
        )

        # check email notifications
        notification = mail.outbox[0]
        self.assertIn("wants to join", notification.subject)
        self.assertEqual(notification.to[0], self.member.email)
        self.assertEqual(len(mail.outbox), 1)

    def test_cannot_have_two_pending_applications(self):
        ApplicationFactory(group=self.group, user=self.applicant)

        # create another application
        self.client.force_login(user=self.applicant)
        answers = faker.text()
        response = self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": answers,},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_apply_again(self):
        ApplicationFactory(
            group=self.group,
            user=self.applicant,
            status=ApplicationStatus.WITHDRAWN.value,
        )

        # create another application
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": faker.text(),},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_apply_with_unverified_account(self):
        user = UserFactory()
        self.client.force_login(user=user)
        response = self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": faker.text(),},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_apply_when_already_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": faker.text(),},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_apply_to_open_group(self):
        open_group = GroupFactory(members=[self.member], is_open=True)
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            "/api/applications/", {"group": open_group.id, "answers": faker.text(),},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestApplicationNotifications(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        mail.outbox = []

    def test_disable_notifications(self):
        self.client.force_login(user=self.member)
        response = self.client.delete(
            "/api/groups/{}/notification_types/{}/".format(
                self.group.id, GroupNotificationType.NEW_APPLICATION,
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create application
        self.client.force_login(user=self.applicant)
        answers = faker.text()
        self.client.post(
            "/api/applications/", {"group": self.group.id, "answers": answers,}
        )

        # no emails should be received by member
        self.assertEqual(len(mail.outbox), 0)


class TestApplicationConversation(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        self.application = ApplicationFactory(group=self.group, user=self.applicant)
        self.conversation = Conversation.objects.get_for_target(self.application)
        mail.outbox = []

    def test_member_replies_in_conversation(self):
        self.client.force_login(user=self.member)
        chat_message = faker.sentence()
        with execute_scheduled_tasks_immediately():
            response = self.client.post(
                "/api/messages/",
                {"conversation": self.conversation.id, "content": chat_message,},
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn("New message in", notification.subject)
        self.assertIn(chat_message, notification.body)

    def test_newcomer_replies_in_conversation(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        mail.outbox = []
        self.client.force_login(user=newcomer)
        chat_message = faker.sentence()
        with execute_scheduled_tasks_immediately():
            response = self.client.post(
                "/api/messages/",
                {"conversation": self.conversation.id, "content": chat_message,},
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertIn("New message in", notification.subject)
        self.assertIn(chat_message, notification.body)

    def test_applicant_replies_in_conversation(self):
        self.client.force_login(user=self.applicant)
        chat_message = faker.sentence()
        with execute_scheduled_tasks_immediately():
            response = self.client.post(
                "/api/messages/",
                {"conversation": self.conversation.id, "content": chat_message,},
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.member.email)
        self.assertIn(
            f"New message in application of {self.applicant.display_name} to {self.group.name}",
            notification.subject,
        )
        self.assertIn(chat_message, notification.body)


class TestApplicationHandling(APITestCase, ExtractPaginationMixin):
    @classmethod
    def setUpTestData(cls):
        cls.applicant = VerifiedUserFactory()
        cls.member = VerifiedUserFactory()
        cls.newcomer = VerifiedUserFactory()
        cls.group = GroupFactory(members=[cls.member], newcomers=[cls.newcomer])
        cls.application = ApplicationFactory(group=cls.group, user=cls.applicant)
        cls.conversation = Conversation.objects.get_for_target(cls.application)

        def make_application():
            applicant = VerifiedUserFactory()
            group = GroupFactory(members=[cls.member])
            ApplicationFactory(group=group, user=applicant)

        [make_application() for _ in range(5)]

    def setUp(self):
        mail.outbox = []

    def test_list_applications_for_group(self):
        self.client.force_login(user=self.member)
        response = self.get_results("/api/applications/?group={}".format(self.group.id))
        self.assertEqual(len(response.data), 1)

    def test_list_applications_for_group_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.get_results("/api/applications/?group={}".format(self.group.id))
        self.assertEqual(len(response.data), 1)

    def test_list_own_applications(self):
        [ApplicationFactory(group=self.group, user=UserFactory()) for _ in range(4)]
        self.client.force_login(user=self.applicant)
        response = self.get_results(
            "/api/applications/?user={}".format(self.applicant.id)
        )
        self.assertEqual(len(response.data), 1)

    def test_list_pending_applications(self):
        self.client.force_login(user=self.member)
        response = self.get_results("/api/applications/?status=pending")
        self.assertEqual(len(response.data), 6)

    def test_accept_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/{}/accept/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "accepted")
        self.assertEqual(response.data["decided_by"], self.member.id)
        self.assertGreaterEqual(
            parse(response.data["decided_at"]),
            timezone.now() - relativedelta(seconds=5),
        )
        self.assertTrue(
            GroupMembership.objects.filter(
                group=self.group, user=self.applicant,
            ).exists()
        )

        # applicant should receive email
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn("was accepted", notification.subject)

        # accepting user gets saved to group membership entry
        self.assertEqual(
            GroupMembership.objects.get(
                group=self.group, user=self.applicant,
            ).added_by,
            self.member,
        )

    def test_cannot_accept_application_twice(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/{}/accept/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            "/api/applications/{}/accept/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_newcomer_cannot_accept_application(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.post(
            "/api/applications/{}/accept/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_decline_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/{}/decline/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "declined")
        self.assertEqual(response.data["decided_by"], self.member.id)
        self.assertGreaterEqual(
            parse(response.data["decided_at"]),
            timezone.now() - relativedelta(seconds=5),
        )
        self.assertFalse(
            GroupMembership.objects.filter(
                group=self.group, user=self.applicant,
            ).exists()
        )

        # applicant should receive email
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn("was declined", notification.subject)

    def test_cannot_decline_application_twice(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/{}/decline/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            "/api/applications/{}/decline/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_newcomer_cannot_decline_application(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.post(
            "/api/applications/{}/decline/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_applicant_cannot_decline_application(self):
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            "/api/applications/{}/decline/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_withdraw_application(self):
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            "/api/applications/{}/withdraw/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "withdrawn")
        self.assertFalse(
            GroupMembership.objects.filter(
                group=self.group, user=self.applicant,
            ).exists()
        )

    def test_cannot_withdraw_application_twice(self):
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            "/api/applications/{}/withdraw/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            "/api/applications/{}/withdraw/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_member_cannot_withdraw_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            "/api/applications/{}/withdraw/".format(self.application.id)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestApplicationUserProfileAccess(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        self.application = ApplicationFactory(group=self.group, user=self.applicant)

    def test_applicant_cannot_view_group_members_profile_information(self):
        self.client.force_login(user=self.applicant)

        member_profile_url = "/api/users/{}/profile/".format(self.member.id)
        response = self.client.get(member_profile_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_group_member_can_view_applicant_profile_information(self):
        self.client.force_login(user=self.member)

        applicant_profile_url = "/api/users/{}/profile/".format(self.applicant.id)
        response = self.client.get(applicant_profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], self.applicant.description)
        self.assertEqual(response.data["email"], self.applicant.email)

        applicant_info_url = "/api/users-info/{}/".format(self.applicant.id)
        response = self.client.get(applicant_info_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], self.applicant.display_name)
