from datetime import timedelta
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from config import settings
from foodsaving.conversations.models import Conversation
from foodsaving.groups.factories import GroupFactory, PlaygroundGroupFactory, InactiveGroupFactory
from foodsaving.groups.models import GroupMembership, GroupStatus
from foodsaving.groups.tasks import process_inactive_users, send_summary_emails, mark_inactive_groups
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups.factories import PickupDateFactory, FeedbackFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory, VerifiedUserFactory


def set_member_inactive(group, user):
    inactive_email_date = timezone.now() - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP + 1)
    inactive_membership = GroupMembership.objects.get(group=group, user=user)
    inactive_membership.lastseen_at = inactive_email_date
    inactive_membership.save()
    return inactive_membership


class TestProcessInactiveUsers(TestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])

        self.active_membership = GroupMembership.objects.get(group=self.group, user=self.active_user)
        self.inactive_membership = set_member_inactive(self.group, self.inactive_user)

        mail.outbox = []

    def test_process_inactive_users_leaves_active_user_alone(self):
        process_inactive_users()
        self.active_membership.refresh_from_db()
        self.assertEqual(self.active_membership.inactive_at, None)

    def test_process_inactive_users_flags_inactive_user(self):
        process_inactive_users()
        self.inactive_membership.refresh_from_db()
        self.assertNotEqual(self.inactive_membership.inactive_at, None)

    def test_process_inactive_users_sends_email(self):
        process_inactive_users()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.inactive_user.email])


class TestProcessInactiveUsersNonActiveGroup(TestCase):
    def setUp(self):
        inactive_user = UserFactory()
        playground_group = PlaygroundGroupFactory(members=[inactive_user])
        inactive_group = InactiveGroupFactory(members=[inactive_user])

        set_member_inactive(playground_group, inactive_user)
        set_member_inactive(inactive_group, inactive_user)

        mail.outbox = []

    def test_dont_send_email_in_playground_group(self):
        process_inactive_users()
        self.assertEqual(len(mail.outbox), 0)


class TestSummaryEmailTask(TestCase):
    def setUp(self):
        self.message_count = 10
        self.pickups_missed_count = 5
        self.feedback_count = 4
        self.new_user_count = 3
        self.pickups_done_count = 8

    def make_activity_in_group(self, group):
        store = StoreFactory(group=group)
        new_users = [VerifiedUserFactory() for _ in range(self.new_user_count)]
        user = new_users[0]

        a_few_days_ago = timezone.now() - relativedelta(days=4)
        with freeze_time(a_few_days_ago, tick=True):
            [group.add_member(u) for u in new_users]

            # a couple of messages
            [group.conversation.messages.create(author=user, content='hello') for _ in range(self.message_count)]

            # missed pickups
            [PickupDateFactory(store=store) for _ in range(self.pickups_missed_count)]

            # fullfilled pickups
            pickups = [
                PickupDateFactory(store=store, max_collectors=1, collectors=[user])
                for _ in range(self.pickups_done_count)
            ]

            # pickup feedback
            [FeedbackFactory(about=pickup, given_by=user) for pickup in pickups[:self.feedback_count]]

    @patch('foodsaving.groups.stats.write_points')
    def test_collects_stats(self, write_points):
        group = GroupFactory()
        self.make_activity_in_group(group)

        write_points.reset_mock()
        mail.outbox = []

        send_summary_emails()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].to), self.new_user_count)
        write_points.assert_called_with([{
            'measurement': 'karrot.email.group_summary',
            'tags': {
                'group': str(group.id)
            },
            'fields': {
                'value': 1,
                'new_user_count': self.new_user_count,
                'email_recipient_count': self.new_user_count,
                'feedback_count': self.feedback_count,
                'pickups_missed_count': self.pickups_missed_count,
                'message_count': self.message_count,
                'pickups_done_count': self.pickups_done_count,
                'has_activity': True,
            },
        }])

    @patch('foodsaving.groups.stats.write_points')
    def test_no_summary_email_if_no_activity_in_group(self, write_points):
        group = GroupFactory(members=[VerifiedUserFactory()])

        write_points.reset_mock()
        mail.outbox = []

        send_summary_emails()

        self.assertEqual(len(mail.outbox), 0)
        write_points.assert_called_with([{
            'measurement': 'karrot.email.group_summary',
            'tags': {
                'group': str(group.id)
            },
            'fields': {
                'value': 1,
                'new_user_count': 0,
                'email_recipient_count': 0,
                'feedback_count': 0,
                'pickups_missed_count': 0,
                'message_count': 0,
                'pickups_done_count': 0,
                'has_activity': False,
            },
        }])


class TestMarkInactiveGroupsTask(TestCase):
    def setUp(self):
        self.group_no_recent_activity = GroupFactory()
        self.group_with_recent_activity = GroupFactory()
        self.user = UserFactory()
        self.date_old = timezone.now() - timedelta(days=settings.NUMBER_OF_DAYS_GROUP_INACTIVE + 3)
        self.date_new = timezone.now() - timedelta(days=settings.NUMBER_OF_DAYS_GROUP_INACTIVE - 3)

    def test_mark_inactive_group_trigger_wall_messages(self):
        conversation_old = Conversation.objects.get_or_create_for_target(self.group_no_recent_activity)
        conversation_old.sync_users([self.user])
        conversation_old.messages.create(author=self.user,
                                         content='hello',
                                         created_at=self.date_old)
        conversation_new = Conversation.objects.get_or_create_for_target(self.group_with_recent_activity)
        conversation_new.sync_users([self.user])
        conversation_new.messages.create(author=self.user,
                                         content='hello',
                                         created_at=self.date_new)
        mark_inactive_groups()
        self.group_no_recent_activity.refresh_from_db()
        self.group_with_recent_activity.refresh_from_db()
        self.assertEqual(self.group_no_recent_activity.status, GroupStatus.INACTIVE.value)
        self.assertEqual(self.group_with_recent_activity.status, GroupStatus.ACTIVE.value)

    def test_mark_inactive_group_trigger_feedback(self):
        store_old = StoreFactory(group=self.group_no_recent_activity)
        store_new = StoreFactory(group=self.group_with_recent_activity)
        pickup_old = PickupDateFactory(store=store_old)
        pickup_new = PickupDateFactory(store=store_new)
        FeedbackFactory(about=pickup_old, given_by=self.user, created_at=self.date_old)
        FeedbackFactory(about=pickup_new, given_by=self.user, created_at=self.date_new)
        mark_inactive_groups()
        self.group_no_recent_activity.refresh_from_db()
        self.group_with_recent_activity.refresh_from_db()
        self.assertEqual(self.group_no_recent_activity.status, GroupStatus.INACTIVE.value)
        self.assertEqual(self.group_with_recent_activity.status, GroupStatus.ACTIVE.value)

    def test_mark_inactive_group_trigger_history(self):
        History.objects.create(
            typus=HistoryTypus.STORE_CREATE,
            group=self.group_no_recent_activity,
            store=StoreFactory(),
            users=[self.user],
            date=self.date_old,
        )
        History.objects.create(
            typus=HistoryTypus.STORE_CREATE,
            group=self.group_with_recent_activity,
            store=StoreFactory(),
            users=[self.user],
            date=self.date_new,
        )
        mark_inactive_groups()
        self.group_no_recent_activity.refresh_from_db()
        self.group_with_recent_activity.refresh_from_db()
        self.assertEqual(self.group_no_recent_activity.status, GroupStatus.INACTIVE.value)
        self.assertEqual(self.group_with_recent_activity.status, GroupStatus.ACTIVE.value)
