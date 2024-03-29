from rest_framework.test import APITestCase

from karrot.applications.factories import ApplicationFactory
from karrot.applications.models import Application, ApplicationStatus
from karrot.conversations.models import Conversation
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.users.factories import VerifiedUserFactory


class TestApplicationConversationModel(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        self.application = ApplicationFactory(group=self.group, user=self.applicant)
        self.conversation = Conversation.objects.get_for_target(self.application)

    def test_member_leaves_group(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).delete()
        self.assertNotIn(
            self.member,
            self.conversation.participants.all(),
        )

    def test_user_erased(self):
        self.applicant.refresh_from_db()  # otherwise user.photo.name is None
        self.applicant.erase()

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.WITHDRAWN.value)

    def test_deleting_application_deletes_conversation(self):
        Application.objects.filter(user=self.applicant, group=self.group).delete()
        self.assertIsNone(Conversation.objects.get_for_target(self.application))

    def test_sets_group(self):
        self.assertEqual(self.conversation.group, self.group)

    def test_withdraw_pending_application_when_user_joins_group(self):
        self.group.add_member(self.applicant)

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.WITHDRAWN.value)
