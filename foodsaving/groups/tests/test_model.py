from datetime import timedelta

from django.db import DataError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from foodsaving.conversations.models import Conversation, ConversationParticipant
from foodsaving.groups.factories import GroupFactory, PlaygroundGroupFactory
from foodsaving.groups.models import Group, GroupMembership, get_default_notification_types
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.pickups.models import to_range
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestGroupModel(TestCase):
    def test_create_fails_if_name_too_long(self):
        with self.assertRaises(DataError):
            Group.objects.create(name='a' * 81)

    def test_create_group_with_same_name_fails(self):
        Group.objects.create(name='abcdef')
        with self.assertRaises(IntegrityError):
            Group.objects.create(name='abcdef')

    def test_notifications_on_by_default(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        membership = GroupMembership.objects.get(user=user, group=group)
        self.assertEqual(get_default_notification_types(), membership.notification_types)
        conversation = Conversation.objects.get_for_target(group)
        conversation_participant = ConversationParticipant.objects.get(conversation=conversation, user=user)
        self.assertTrue(conversation_participant.email_notifications)

    def test_no_notifications_by_default_in_playground(self):
        user = UserFactory()
        group = PlaygroundGroupFactory(members=[user])
        membership = GroupMembership.objects.get(user=user, group=group)
        self.assertEqual([], membership.notification_types)
        conversation = Conversation.objects.get_for_target(group)
        conversation_participant = ConversationParticipant.objects.get(conversation=conversation, user=user)
        self.assertFalse(conversation_participant.email_notifications)

    def test_uses_default_application_questions_if_not_specified(self):
        group = GroupFactory(application_questions='')
        self.assertIn('Hey there', group.get_application_questions_or_default())


class TestGroupMembershipModel(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user])
        self.other_group = GroupFactory(members=[self.user, self.other_user])
        self.store = StoreFactory(group=self.group)
        self.other_store = StoreFactory(group=self.other_group)

    def test_pickup_active_within(self):
        PickupDateFactory(store=self.store, date=to_range(timezone.now() - timedelta(days=2)), collectors=[self.user])
        PickupDateFactory(
            store=self.store, date=to_range(timezone.now() - timedelta(days=9)), collectors=[self.other_user]
        )
        memberships = self.group.groupmembership_set.pickup_active_within(days=7)
        self.assertEqual(memberships.count(), 1)

    def test_pickup_active_within_does_not_double_count(self):
        for _ in range(1, 10):
            PickupDateFactory(
                store=self.store, date=to_range(timezone.now() - timedelta(days=2)), collectors=[self.user]
            )
            PickupDateFactory(
                store=self.store, date=to_range(timezone.now() - timedelta(days=9)), collectors=[self.other_user]
            )
        memberships = self.group.groupmembership_set.pickup_active_within(days=7)
        self.assertEqual(memberships.count(), 1)

    def test_does_not_count_from_other_groups(self):
        PickupDateFactory(
            store=self.other_store, date=to_range(timezone.now() - timedelta(days=2)), collectors=[self.user]
        )
        memberships = self.group.groupmembership_set.pickup_active_within(days=7)
        self.assertEqual(memberships.count(), 0)
