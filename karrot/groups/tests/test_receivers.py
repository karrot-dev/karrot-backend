from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from karrot.conversations.models import Conversation, ConversationParticipant
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.users.factories import UserFactory


class TestConversationReceiver(TestCase):
    def setUp(self):
        self.invited_by = UserFactory()
        self.group = GroupFactory(members=[self.invited_by])
        self.user = UserFactory()
        self.invited_at = timezone.now()

    def test_creates_conversation(self):
        group = GroupFactory()
        conversation = self.get_conversation_for_group(group)
        self.assertIsInstance(conversation, Conversation, "Did not have a conversation")

    def test_conversation_deleted(self):
        group = GroupFactory()
        conversation_id = group.conversation.id
        group.delete()
        with self.assertRaises(Conversation.DoesNotExist):
            self.assertIsNone(Conversation.objects.get(pk=conversation_id))

    def test_adds_participant(self):
        group = GroupFactory()
        user = UserFactory()
        GroupMembership.objects.create(group=group, user=user)
        conversation = self.get_conversation_for_group(group)
        self.assertIn(user, conversation.participants.all(), "Conversation did not have user in")

    def test_adds_participant_marks_existing_messages_as_read(self):
        existing_member = UserFactory()
        group = GroupFactory(members=[existing_member])

        group.conversation.messages.create(author=existing_member, content="foo")
        second_message = group.conversation.messages.create(author=existing_member, content="bar")

        new_member = UserFactory()
        GroupMembership.objects.create(group=group, user=new_member)

        new_participant = ConversationParticipant.objects.get(user=new_member, conversation=group.conversation)
        self.assertTrue(new_participant.seen_up_to == second_message)

    def test_removes_participant(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        GroupMembership.objects.filter(group=group, user=user).delete()
        conversation = self.get_conversation_for_group(group)
        self.assertNotIn(user, conversation.participants.all(), "Conversation still had user in")

    def get_conversation_for_group(self, group):
        return Conversation.objects.filter(
            target_id=group.id, target_type=ContentType.objects.get_for_model(group)
        ).first()


class TestSendStatistics(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])

    @patch("karrot.groups.stats.write_points")
    def test_send_group_join_stats(self, write_mock):
        self.group.add_member(self.user)
        self.assertTrue(write_mock.called)

    @patch("karrot.groups.stats.write_points")
    def test_non_send_group_join_stats_on_update(self, write_mock):
        membership = GroupMembership.objects.get(group=self.group, user=self.member)
        membership.inactive_at = None
        membership.save()
        self.assertFalse(write_mock.called)
