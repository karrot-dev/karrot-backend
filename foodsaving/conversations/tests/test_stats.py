from django.test import TestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.stats import tags_for_conversation
from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory


class TestConversationStats(TestCase):
    def test_tags_for_group_conversation(self):
        group = GroupFactory()
        tags = tags_for_conversation(group.conversation)
        self.assertEqual(tags, {'type': 'group', 'group': group.id})

    def test_tags_for_pickup_conversation(self):
        group = GroupFactory()
        store = StoreFactory(group=group)
        pickup = PickupDateFactory(store=store)
        tags = tags_for_conversation(pickup.conversation)
        self.assertEqual(tags, {'type': 'pickup', 'group': group.id})

    def test_tags_for_private_conversation(self):
        conversation = ConversationFactory(is_private=True)
        tags = tags_for_conversation(conversation)
        self.assertEqual(tags, {'type': 'private'})

    def test_tags_for_other_conversation(self):
        conversation = ConversationFactory()
        tags = tags_for_conversation(conversation)
        self.assertEqual(tags, {'type': 'unknown'})
