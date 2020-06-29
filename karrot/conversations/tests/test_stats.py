from django.test import TestCase

from karrot.conversations.factories import ConversationFactory
from karrot.conversations.stats import conversation_tags
from karrot.groups.factories import GroupFactory
from karrot.activities.factories import ActivityFactory
from karrot.places.factories import PlaceFactory


class TestConversationStats(TestCase):
    def test_tags_for_group_conversation(self):
        group = GroupFactory()
        tags = conversation_tags(group.conversation)
        self.assertEqual(tags, {
            'type': 'group',
            'group': str(group.id),
            'group_status': group.status,
        })

    def test_tags_for_activity_conversation(self):
        group = GroupFactory()
        place = PlaceFactory(group=group)
        activity = ActivityFactory(place=place)
        tags = conversation_tags(activity.conversation)
        self.assertEqual(tags, {
            'type': 'activity',
            'group': str(group.id),
            'group_status': group.status,
        })

    def test_tags_for_private_conversation(self):
        conversation = ConversationFactory(is_private=True)
        tags = conversation_tags(conversation)
        self.assertEqual(tags, {'type': 'private'})

    def test_tags_for_other_conversation(self):
        conversation = ConversationFactory()
        tags = conversation_tags(conversation)
        self.assertEqual(tags, {'type': 'unknown'})
