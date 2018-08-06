from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.models import Conversation
from foodsaving.groups.factories import GroupFactory
from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.groups.models import GroupMembership, GroupNotificationType
from foodsaving.applications.models import GroupApplicationStatus
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.users.serializers import UserSerializer
from foodsaving.utils.tests.fake import faker


class TestCreateGroupApplication(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(editors=[self.member])
        mail.outbox = []

    def test_apply_for_group(self):
        self.client.force_login(user=self.applicant)
        answers = faker.text()

        # create application
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': self.group.id,
                'answers': answers,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        data = response.data
        application_id = data['id']
        del data['id']
        conversation_id = data['conversation']
        created_at = parse(data['created_at'])
        data['created_at'] = created_at
        self.assertEqual(
            data,
            {
                'questions': self.group.application_questions,
                'answers': answers,
                'user': UserSerializer(self.applicant).data,
                'group': self.group.id,
                'conversation': conversation_id,
                'status': 'pending',
                'created_at': created_at,
                'decided_by': None,
                'decided_at': None,
            },
        )

        # check conversation
        conversation_response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(conversation_response.status_code, status.HTTP_200_OK)
        for user_id in (self.applicant.id, self.member.id):
            self.assertIn(user_id, conversation_response.data['participants'])
        message_response = self.get_results('/api/messages/?conversation={}'.format(conversation_id))
        self.assertEqual(len(message_response.data), 0)

        # list application
        application_list_response = self.client.get('/api/group-applications/')
        self.assertEqual(application_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(application_list_response.data), 1)
        data = application_list_response.data[0]
        data['created_at'] = parse(data['created_at'])
        self.assertEqual(
            data,
            {
                'id': application_id,
                'questions': self.group.application_questions,
                'answers': answers,
                'user': UserSerializer(self.applicant).data,
                'group': self.group.id,
                'conversation': conversation_id,
                'status': 'pending',
                'created_at': created_at,
                'decided_by': None,
                'decided_at': None,
            },
        )

        # check email notifications
        notification = mail.outbox[0]
        self.assertIn('wants to join', notification.subject)
        self.assertEqual(notification.to[0], self.member.email)
        self.assertEqual(len(mail.outbox), 1)

    def test_cannot_have_two_pending_applications(self):
        GroupApplicationFactory(group=self.group, user=self.applicant)

        # create another application
        self.client.force_login(user=self.applicant)
        answers = faker.text()
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': self.group.id,
                'answers': answers,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_apply_again(self):
        GroupApplicationFactory(
            group=self.group,
            user=self.applicant,
            status=GroupApplicationStatus.WITHDRAWN.value,
        )

        # create another application
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': self.group.id,
                'answers': faker.text(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_apply_with_unverified_account(self):
        user = UserFactory()
        self.client.force_login(user=user)
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': self.group.id,
                'answers': faker.text(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_apply_when_already_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': self.group.id,
                'answers': faker.text(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_apply_to_open_group(self):
        open_group = GroupFactory(editors=[self.member], is_open=True)
        self.client.force_login(user=self.applicant)
        response = self.client.post(
            '/api/group-applications/',
            {
                'group': open_group.id,
                'answers': faker.text(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestApplicationNotifications(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(editors=[self.member])
        mail.outbox = []

    def test_disable_notifications(self):
        self.client.force_login(user=self.member)
        response = self.client.delete(
            '/api/groups/{}/notification_types/{}/'.format(
                self.group.id,
                GroupNotificationType.NEW_APPLICATION,
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create application
        self.client.force_login(user=self.applicant)
        answers = faker.text()
        self.client.post('/api/group-applications/', {
            'group': self.group.id,
            'answers': answers,
        })

        # no emails should be received by member
        self.assertEqual(len(mail.outbox), 0)


class TestApplicationConversation(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(editors=[self.member])
        self.application = GroupApplicationFactory(group=self.group, user=self.applicant)
        self.conversation = Conversation.objects.get_for_target(self.application)
        mail.outbox = []

    def test_member_replies_in_conversation(self):
        self.client.force_login(user=self.member)
        chat_message = faker.sentence()
        response = self.client.post(
            '/api/messages/', {
                'conversation': self.conversation.id,
                'content': chat_message,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn('New message in', notification.subject)
        self.assertIn(chat_message, notification.body)

    def test_newcomer_replies_in_conversation(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        mail.outbox = []
        self.client.force_login(user=newcomer)
        chat_message = faker.sentence()
        response = self.client.post(
            '/api/messages/', {
                'conversation': self.conversation.id,
                'content': chat_message,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertIn('New message in', notification.subject)
        self.assertIn(chat_message, notification.body)

    def test_applicant_replies_in_conversation(self):
        self.client.force_login(user=self.applicant)
        chat_message = faker.sentence()
        response = self.client.post(
            '/api/messages/', {
                'conversation': self.conversation.id,
                'content': chat_message,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.member.email)
        self.assertIn('New message in', notification.subject)
        self.assertIn(chat_message, notification.body)


class TestApplicationHandling(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.group = GroupFactory(editors=[self.member], newcomers=[self.newcomer])
        self.application = GroupApplicationFactory(group=self.group, user=self.applicant)
        self.conversation = Conversation.objects.get_for_target(self.application)

        def make_application():
            applicant = VerifiedUserFactory()
            group = GroupFactory(editors=[self.member])
            GroupApplicationFactory(group=group, user=applicant)

        [make_application() for _ in range(5)]

        mail.outbox = []

    def test_list_applications_for_group(self):
        self.client.force_login(user=self.member)
        response = self.get_results('/api/group-applications/?group={}'.format(self.group.id))
        self.assertEqual(len(response.data), 1)

    def test_list_applications_for_group_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.get_results('/api/group-applications/?group={}'.format(self.group.id))
        self.assertEqual(len(response.data), 1)

    def test_list_own_applications(self):
        [GroupApplicationFactory(group=self.group, user=UserFactory()) for _ in range(4)]
        self.client.force_login(user=self.applicant)
        response = self.get_results('/api/group-applications/?user={}'.format(self.applicant.id))
        self.assertEqual(len(response.data), 1)

    def test_list_pending_applications(self):
        [GroupApplicationFactory(group=self.group, user=self.applicant, status='withdrawn') for _ in range(4)]
        self.client.force_login(user=self.applicant)
        response = self.get_results('/api/group-applications/?status={}'.format(self.applicant.id))
        self.assertEqual(len(response.data), 1)

    def test_accept_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/group-applications/{}/accept/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'accepted')
        self.assertEqual(response.data['decided_by'], self.member.id)
        self.assertGreaterEqual(parse(response.data['decided_at']), timezone.now() - relativedelta(seconds=5))
        self.assertTrue(GroupMembership.objects.filter(
            group=self.group,
            user=self.applicant,
        ).exists())

        # applicant should receive email
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn('was accepted', notification.subject)

        # accepting user gets saved to group membership entry
        self.assertEqual(GroupMembership.objects.get(
            group=self.group,
            user=self.applicant,
        ).added_by, self.member)

    def test_newcomer_cannot_accept_application(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.post('/api/group-applications/{}/accept/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_decline_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/group-applications/{}/decline/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'declined')
        self.assertEqual(response.data['decided_by'], self.member.id)
        self.assertGreaterEqual(parse(response.data['decided_at']), timezone.now() - relativedelta(seconds=5))
        self.assertFalse(GroupMembership.objects.filter(
            group=self.group,
            user=self.applicant,
        ).exists())

        # applicant should receive email
        notification = mail.outbox[0]
        self.assertEqual(notification.to[0], self.applicant.email)
        self.assertIn('was declined', notification.subject)

    def test_newcomer_cannot_decline_application(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.post('/api/group-applications/{}/decline/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_applicant_cannot_decline_application(self):
        self.client.force_login(user=self.applicant)
        response = self.client.post('/api/group-applications/{}/decline/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_withdraw_application(self):
        self.client.force_login(user=self.applicant)
        response = self.client.post('/api/group-applications/{}/withdraw/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'withdrawn')
        self.assertFalse(GroupMembership.objects.filter(
            group=self.group,
            user=self.applicant,
        ).exists())

    def test_group_member_cannot_withdraw_application(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/group-applications/{}/withdraw/'.format(self.application.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
