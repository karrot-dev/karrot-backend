from datetime import timedelta

from django.db import DataError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from karrot.conversations.models import Conversation, ConversationParticipant
from karrot.groups.factories import GroupFactory, PlaygroundGroupFactory
from karrot.groups.models import Group, get_default_notification_types
from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory
from karrot.groups import themes


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
        group = GroupFactory()
        membership = group.groupmembership_set.create(user=user)
        self.assertEqual(get_default_notification_types(), membership.notification_types)
        conversation = Conversation.objects.get_for_target(group)
        conversation_participant = ConversationParticipant.objects.get(conversation=conversation, user=user)
        self.assertFalse(conversation_participant.muted)

    def test_no_notifications_by_default_in_playground(self):
        user = UserFactory()
        group = PlaygroundGroupFactory()
        membership = group.groupmembership_set.create(user=user)
        self.assertEqual([], membership.notification_types)
        conversation = Conversation.objects.get_for_target(group)
        conversation_participant = ConversationParticipant.objects.get(conversation=conversation, user=user)
        self.assertTrue(conversation_participant.muted)

    def test_uses_default_application_questions_if_not_specified(self):
        group = GroupFactory(application_questions='')
        self.assertIn('Hey there', group.get_application_questions_or_default())


class TestGroupMembershipModel(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user])
        self.other_group = GroupFactory(members=[self.user, self.other_user])
        self.place = PlaceFactory(group=self.group)
        self.other_place = PlaceFactory(group=self.other_group)

    def test_activity_active_within(self):
        ActivityFactory(place=self.place, date=to_range(timezone.now() - timedelta(days=2)), participants=[self.user])
        ActivityFactory(
            place=self.place, date=to_range(timezone.now() - timedelta(days=9)), participants=[self.other_user]
        )
        memberships = self.group.groupmembership_set.activity_active_within(days=7)
        self.assertEqual(memberships.count(), 1)

    def test_activity_active_within_does_not_double_count(self):
        for _ in range(1, 10):
            ActivityFactory(
                place=self.place, date=to_range(timezone.now() - timedelta(days=2)), participants=[self.user]
            )
            ActivityFactory(
                place=self.place, date=to_range(timezone.now() - timedelta(days=9)), participants=[self.other_user]
            )
        memberships = self.group.groupmembership_set.activity_active_within(days=7)
        self.assertEqual(memberships.count(), 1)

    def test_does_not_count_from_other_groups(self):
        ActivityFactory(
            place=self.other_place, date=to_range(timezone.now() - timedelta(days=2)), participants=[self.user]
        )
        memberships = self.group.groupmembership_set.activity_active_within(days=7)
        self.assertEqual(memberships.count(), 0)


class TestGroupManager(TestCase):

    # test if setting a default status and theme via settings works

    # set each setting individually
    @override_settings(GROUP_THEME_DEFAULT=themes.GroupTheme.FOODSAVING)
    def test_create_group_theme_default_foodsaving(self):
        group = GroupFactory()
        self.assertEqual(themes.GroupTheme.FOODSAVING.value, group.theme)

    @override_settings(GROUP_THEME_DEFAULT=themes.GroupTheme.GENERAL)
    def test_create_group_theme_default_general(self):
        group = GroupFactory()
        self.assertEqual(themes.GroupTheme.GENERAL.value, group.theme)

    @override_settings(GROUP_THEME_DEFAULT=themes.GroupTheme.BIKEKITCHEN)
    def test_create_group_theme_default_bikekitchen(self):
        group = GroupFactory()
        self.assertEqual(themes.GroupTheme.BIKEKITCHEN.value, group.theme)
