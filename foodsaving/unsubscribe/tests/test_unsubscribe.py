from django.test import TestCase

from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.unsubscribe.utils import unsubscribe_from_all_conversations_in_group, generate_token, parse_token
from foodsaving.users.factories import UserFactory


class TestTokenParser(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])

    def test_with_a_conversation(self):
        token = generate_token(self.user, self.group, conversation=self.group.conversation)
        data = parse_token(token)
        self.assertEqual(self.user, data['user'])
        self.assertEqual(self.group, data['group'])
        self.assertEqual(self.group.conversation, data['conversation'])

    def test_with_a_thread(self):
        thread = self.group.conversation.messages.create(author=self.user, content='foo')
        self.group.conversation.messages.create(author=self.user, content='foo reply', thread=thread)
        token = generate_token(self.user, self.group, thread=thread)
        data = parse_token(token)
        self.assertEqual(self.user, data['user'])
        self.assertEqual(self.group, data['group'])
        self.assertEqual(thread, data['thread'])


class TestUnsubscribeFromAllConversationsInGroup(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.store = StoreFactory(group=self.group)
        self.other_group = GroupFactory(members=[self.user])
        self.other_store = StoreFactory(group=self.other_group)

    def test_unsubscribe_from_group_wall(self):
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertFalse(participant.get().email_notifications)

    def test_does_not_unsubscribe_from_other_group_wall(self):
        participant = self.other_group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().email_notifications)

    def test_unsubscribe_from_group_wall_thread(self):
        thread = self.group.conversation.messages.create(author=self.user, content='foo')
        self.group.conversation.messages.create(author=self.user, content='foo reply', thread=thread)
        participant = thread.participants.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().muted)

    def test_unsubscribe_from_pickup_conversation(self):
        pickup = PickupDateFactory(store=self.store, collectors=[self.user])
        participant = pickup.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertFalse(participant.get().email_notifications)

    def test_does_not_unsubscribe_from_other_group_pickup_conversations(self):
        pickup = PickupDateFactory(store=self.other_store, collectors=[self.user])
        participant = pickup.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().email_notifications)

    def test_unsubscribe_from_group_applications(self):
        application = GroupApplicationFactory(group=self.group, user=UserFactory())
        participant = application.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertFalse(participant.get().email_notifications)
