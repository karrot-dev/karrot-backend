from rest_framework.test import APITestCase

from foodsaving.conversations.models import Conversation
from foodsaving.groups.factories import GroupFactory, GroupApplicationFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.applications.models import GroupApplication
from foodsaving.users.factories import VerifiedUserFactory


class TestApplicationConversationModel(APITestCase):
    def setUp(self):
        self.applicant = VerifiedUserFactory()
        self.member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member])
        self.application = GroupApplicationFactory(group=self.group, user=self.applicant)
        self.conversation = Conversation.objects.get_for_target(self.application)

    def test_member_leaves_group(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).delete()
        self.assertNotIn(
            self.member,
            self.conversation.participants.all(),
        )

    def test_deleting_application_deletes_conversation(self):
        GroupApplication.objects.filter(user=self.applicant, group=self.group).delete()
        self.assertIsNone(
            Conversation.objects.get_for_target(self.application)
        )

