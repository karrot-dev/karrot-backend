from karrot.conversations.models import ConversationParticipant
from karrot.groups.factories import GroupFactory
from karrot.users.factories import UserFactory
from rest_framework.test import APITestCase


class TestApplicationReceivers(APITestCase):
    def setUp(self):
        self.new_member = UserFactory()
        self.existing_member = UserFactory()
        self.group = GroupFactory(members=[self.existing_member], application_questions='')

    def test_group_add_member_marks_existing_messages_as_read(self):
        self.group.conversation.messages.create(author=self.existing_member, content='foo')
        second_message = self.group.conversation.messages.create(author=self.existing_member, content='bar')

        self.group.add_member(self.new_member)

        new_participant = ConversationParticipant.objects.get(
            user=self.new_member, conversation=self.group.conversation
        )
        self.assertTrue(new_participant.seen_up_to == second_message)
