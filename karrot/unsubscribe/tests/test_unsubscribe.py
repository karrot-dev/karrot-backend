from django.test import TestCase

from karrot.applications.factories import ApplicationFactory
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupNotificationType
from karrot.pickups.factories import PickupDateFactory
from karrot.places.factories import PlaceFactory
from karrot.unsubscribe.utils import unsubscribe_from_all_conversations_in_group, generate_token, parse_token, \
    unsubscribe_from_notification_type
from karrot.users.factories import UserFactory


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

    def test_with_notification_types(self):
        token = generate_token(
            self.user, self.group, notification_type=GroupNotificationType.DAILY_PICKUP_NOTIFICATION
        )
        data = parse_token(token)
        self.assertEqual(data['notification_type'], 'daily_pickup_notification')


class TestUnsubscribeFromNotificationTypes(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])

    def test_unsubscribe_from_weekly_summaries(self):
        notification_types = self.group.groupmembership_set.filter(user=self.user).values_list(
            'notification_types',
            flat=True,
        )
        self.assertIn(GroupNotificationType.WEEKLY_SUMMARY, notification_types.get())
        unsubscribe_from_notification_type(self.user, self.group, GroupNotificationType.WEEKLY_SUMMARY)
        self.assertNotIn(GroupNotificationType.WEEKLY_SUMMARY, notification_types.get())


class TestUnsubscribeFromAllConversationsInGroup(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.place = PlaceFactory(group=self.group)
        self.other_group = GroupFactory(members=[self.user])
        self.other_place = PlaceFactory(group=self.other_group)

    def test_unsubscribe_from_group_wall(self):
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().muted)

    def test_does_not_unsubscribe_from_other_group_wall(self):
        participant = self.other_group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertFalse(participant.get().muted)

    def test_unsubscribe_from_group_wall_thread(self):
        thread = self.group.conversation.messages.create(author=self.user, content='foo')
        self.group.conversation.messages.create(author=self.user, content='foo reply', thread=thread)
        participant = thread.participants.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().muted)

    def test_unsubscribe_from_all_group_notifications(self):
        membership = self.group.groupmembership_set.filter(user=self.user)
        self.assertEqual(
            membership.get().notification_types, [
                'weekly_summary',
                'daily_pickup_notification',
                'new_application',
            ]
        )
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertEqual(membership.get().notification_types, [])

    def test_unsubscribe_from_pickup_conversation(self):
        pickup = PickupDateFactory(place=self.place, collectors=[self.user])
        participant = pickup.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().muted)

    def test_does_not_unsubscribe_from_other_group_pickup_conversations(self):
        pickup = PickupDateFactory(place=self.other_place, collectors=[self.user])
        participant = pickup.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertFalse(participant.get().muted)

    def test_unsubscribe_from_applications(self):
        application = ApplicationFactory(group=self.group, user=UserFactory())
        participant = application.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        unsubscribe_from_all_conversations_in_group(self.user, self.group)
        self.assertTrue(participant.get().muted)
