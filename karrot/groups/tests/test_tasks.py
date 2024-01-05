import datetime
from datetime import timedelta
from unittest.mock import patch

import pytz
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from config import settings
from karrot.activities.factories import ActivityFactory, FeedbackFactory
from karrot.groups.emails import calculate_group_summary_dates, prepare_group_summary_data, prepare_group_summary_emails
from karrot.groups.factories import GroupFactory, InactiveGroupFactory, PlaygroundGroupFactory
from karrot.groups.models import GroupMembership, GroupStatus
from karrot.groups.roles import GROUP_MEMBER
from karrot.groups.tasks import mark_inactive_groups, process_inactive_users, send_summary_emails
from karrot.history.models import History, HistoryTypus
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory, VerifiedUserFactory


def set_lastseen_at(group, user, **kwargs):
    membership = GroupMembership.objects.get(group=group, user=user)
    membership.lastseen_at = timezone.now() - relativedelta(**kwargs)
    membership.save()
    return membership


def set_inactive_at(group, user, **kwargs):
    membership = GroupMembership.objects.get(group=group, user=user)
    membership.inactive_at = timezone.now() - relativedelta(**kwargs)
    membership.save()
    return membership


def set_removal_notification_at(group, user, **kwargs):
    membership = GroupMembership.objects.get(group=group, user=user)
    membership.removal_notification_at = timezone.now() - relativedelta(**kwargs)
    membership.save()
    return membership


class TestProcessInactiveUsers(TestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])

        self.active_membership = GroupMembership.objects.get(group=self.group, user=self.active_user)
        self.inactive_membership = set_lastseen_at(
            self.group, self.inactive_user, days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP + 1
        )

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
        self.assertEqual(mail.outbox[0].subject, f"{self.group.name} is missing you!")


class TestProcessInactiveUsersForRemoval(TestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])

        self.active_membership = GroupMembership.objects.get(group=self.group, user=self.active_user)
        set_lastseen_at(self.group, self.inactive_user, days=99999)
        self.inactive_membership = set_inactive_at(
            self.group,
            self.inactive_user,
            months=settings.NUMBER_OF_INACTIVE_MONTHS_UNTIL_REMOVAL_FROM_GROUP_NOTIFICATION,
        )

        mail.outbox = []

    def test_notifies_user_about_removal(self):
        self.assertIsNone(self.inactive_membership.removal_notification_at)
        process_inactive_users()
        self.inactive_membership.refresh_from_db()
        self.assertIsNotNone(self.inactive_membership.removal_notification_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.inactive_user.email])
        self.assertEqual(mail.outbox[0].subject, f"{self.group.name} is really missing you!")


class TestProcessInactiveUsersRemovesOldUsers(TestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])

        self.active_membership = GroupMembership.objects.get(group=self.group, user=self.active_user)
        set_lastseen_at(self.group, self.inactive_user, days=99999)
        set_inactive_at(self.group, self.inactive_user, days=99999)
        self.inactive_membership = set_removal_notification_at(
            self.group,
            self.inactive_user,
            days=settings.NUMBER_OF_DAYS_AFTER_REMOVAL_NOTIFICATION_WE_ACTUALLY_REMOVE_THEM,
        )
        mail.outbox = []

    def test_removes_old_users(self):
        member = self.group.members.filter(pk=self.inactive_user.id)
        history = History.objects.filter(
            typus=HistoryTypus.GROUP_LEAVE_INACTIVE, users__in=[self.inactive_user], group=self.group
        )
        self.assertTrue(member.exists())
        self.assertFalse(history.exists())
        process_inactive_users()
        self.assertFalse(member.exists())
        self.assertTrue(history.exists())
        self.assertEqual(len(mail.outbox), 0)


class TestProcessInactiveUsersNonActiveGroup(TestCase):
    def setUp(self):
        inactive_user = UserFactory()
        playground_group = PlaygroundGroupFactory(members=[inactive_user])
        inactive_group = InactiveGroupFactory(members=[inactive_user])

        set_lastseen_at(playground_group, inactive_user, days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP + 1)
        set_lastseen_at(inactive_group, inactive_user, days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP + 1)

        mail.outbox = []

    def test_dont_send_email_in_playground_group(self):
        process_inactive_users()
        self.assertEqual(len(mail.outbox), 0)


class TestSummaryEmailTask(TestCase):
    def setUp(self):
        self.message_count = 10
        self.activities_missed_count = 5
        self.feedback_count = 4
        self.new_user_count = 3
        self.activities_done_count = 8

    def make_activity_in_group(self, group):
        place = PlaceFactory(group=group)
        new_users = [VerifiedUserFactory() for _ in range(self.new_user_count)]
        user = new_users[0]

        a_few_days_ago = timezone.now() - relativedelta(days=4)
        with freeze_time(a_few_days_ago, tick=True):
            [group.add_member(u) for u in new_users]

            # a couple of messages
            [group.conversation.messages.create(author=user, content="hello") for _ in range(self.message_count)]

            # missed activities
            [ActivityFactory(place=place) for _ in range(self.activities_missed_count)]

            # fullfilled activities
            activities = [
                ActivityFactory(
                    place=place,
                    participant_types=[{"role": GROUP_MEMBER, "max_participants": 1}],
                    participants=[user],
                )
                for _ in range(self.activities_done_count)
            ]

            # activity feedback
            [FeedbackFactory(about=activity, given_by=user) for activity in activities[: self.feedback_count]]

    def test_summary_email_dates_printed_correctly(self):
        mail.outbox = []
        with timezone.override(timezone.utc), freeze_time(datetime.datetime(2018, 8, 19)):  # Sunday
            group = GroupFactory()
            self.make_activity_in_group(group)
            from_date, to_date = calculate_group_summary_dates(group)
            context = prepare_group_summary_data(group, from_date, to_date)
            emails = prepare_group_summary_emails(group, context)
            self.assertGreater(len(emails), 0)
            email = emails[0]
            expected_format = "Sunday, August 12, 2018 to Saturday, August 18, 2018"
            self.assertIn(expected_format, email.body)

    def test_summary_emails_send_at_8am_localtime(self):
        group = GroupFactory(timezone=pytz.timezone("Europe/Berlin"))
        # 6am UTC is 8am in this timezone
        with timezone.override(timezone.utc), freeze_time(datetime.datetime(2018, 8, 19, 6, 0, 0, tzinfo=pytz.utc)):
            self.make_activity_in_group(group)
            mail.outbox = []
            send_summary_emails()
            self.assertEqual(len(mail.outbox), self.new_user_count)

    def test_summary_emails_do_not_send_at_other_times(self):
        group = GroupFactory(timezone=pytz.timezone("Europe/Berlin"))
        # 6am UTC is 8am in this timezone
        with timezone.override(timezone.utc), freeze_time(datetime.datetime(2018, 8, 19, 7, 0, 0, tzinfo=pytz.utc)):
            self.make_activity_in_group(group)
            mail.outbox = []
            send_summary_emails()
            self.assertEqual(len(mail.outbox), 0)

    @patch("karrot.groups.stats.write_points")
    def test_collects_stats(self, write_points):
        group = GroupFactory()

        with freeze_time(datetime.datetime(2018, 8, 19, 6, 0, 0, tzinfo=pytz.utc)):
            self.make_activity_in_group(group)
            write_points.reset_mock()
            mail.outbox = []
            send_summary_emails()

        self.assertEqual(len(mail.outbox), self.new_user_count)
        write_points.assert_called_with(
            [
                {
                    "measurement": "karrot.email.group_summary",
                    "tags": {
                        "group": str(group.id),
                        "group_status": "active",
                    },
                    "fields": {
                        "value": 1,
                        "new_user_count": self.new_user_count,
                        "email_recipient_count": self.new_user_count,
                        "feedback_count": self.feedback_count,
                        "activities_missed_count": self.activities_missed_count,
                        "message_count": self.message_count,
                        "activities_done_count": self.activities_done_count,
                        "has_activity": True,
                    },
                }
            ]
        )

    @patch("karrot.groups.stats.write_points")
    def test_no_summary_email_if_no_activity_in_group(self, write_points):
        group = GroupFactory(members=[VerifiedUserFactory()])

        with freeze_time(datetime.datetime(2018, 8, 19, 6, 0, 0, tzinfo=pytz.utc)):
            write_points.reset_mock()
            mail.outbox = []
            send_summary_emails()

        self.assertEqual(len(mail.outbox), 0)
        write_points.assert_called_with(
            [
                {
                    "measurement": "karrot.email.group_summary",
                    "tags": {
                        "group": str(group.id),
                        "group_status": "active",
                    },
                    "fields": {
                        "value": 1,
                        "new_user_count": 0,
                        "email_recipient_count": 0,
                        "feedback_count": 0,
                        "activities_missed_count": 0,
                        "message_count": 0,
                        "activities_done_count": 0,
                        "has_activity": False,
                    },
                }
            ]
        )


class TestMarkInactiveGroupsTask(TestCase):
    def test_groups_marked_inactive(self):
        recent_treshold = timezone.now() - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_GROUP_INACTIVE)
        group_without_recent_activity = GroupFactory(last_active_at=recent_treshold - timedelta(days=3))
        group_with_recent_activity = GroupFactory(last_active_at=recent_treshold + timedelta(days=3))
        mark_inactive_groups()
        group_without_recent_activity.refresh_from_db()
        group_with_recent_activity.refresh_from_db()
        self.assertEqual(group_without_recent_activity.status, GroupStatus.INACTIVE.value)
        self.assertEqual(group_with_recent_activity.status, GroupStatus.ACTIVE.value)
