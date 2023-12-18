from contextlib import contextmanager
from random import randint
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone
from factory.django import mute_signals
from freezegun import freeze_time
from rest_framework.test import APITestCase

from karrot.activities import tasks
from karrot.activities.factories import ActivityFactory
from karrot.activities.tests.test_activities_api import APPROVED
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.activities.models import to_range
from karrot.activities.tasks import daily_activity_notifications, fetch_activity_notification_data_for_group
from karrot.groups.roles import GROUP_MEMBER, GROUP_EDITOR
from karrot.places.factories import PlaceFactory
from karrot.places.models import PlaceStatus, PlaceSubscription
from karrot.subscriptions.factories import WebPushSubscriptionFactory
from karrot.users.factories import VerifiedUserFactory, UserFactory
from karrot.utils.frontend_urls import place_url


@contextmanager
def group_timezone_at(group, **kwargs):
    with timezone.override(group.timezone):
        datetime = timezone.localtime(timezone=group.timezone).replace(**kwargs)
        with freeze_time(datetime, tick=True):
            yield


@patch("karrot.activities.tasks.notify_subscribers")
class TestActivityReminderTask(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.other_user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user])
        self.place = PlaceFactory(group=self.group, subscribers=[self.user, self.other_user])
        self.activity = ActivityFactory(place=self.place)
        with mute_signals(post_save):
            self.subscriptions = [WebPushSubscriptionFactory(user=self.user)]

    def test_activity_reminder_notifies_subscribers(self, notify_subscribers):
        participant = self.activity.add_participant(self.user)
        notify_subscribers.reset_mock()
        tasks.activity_reminder.call_local(participant.id)
        args, kwargs = notify_subscribers.call_args
        subscriptions = kwargs["subscriptions"]
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0], self.subscriptions[0])
        self.assertIn(
            f"/group/{self.group.id}/place/{self.place.id}/activities/{self.activity.id}/detail",
            kwargs["url"],
        )
        self.assertIn(
            "Upcoming {}".format(self.activity.activity_type.name),
            kwargs["title"],
        )
        self.assertIn(
            self.place.name,
            kwargs["body"],
        )

    def test_does_not_send_for_disabled_activity(self, notify_subscribers):
        self.activity.is_disabled = True
        self.activity.save()
        participant = self.activity.add_participant(self.user)
        notify_subscribers.reset_mock()
        tasks.activity_reminder.call_local(participant.id)
        self.assertEqual(notify_subscribers.call_count, 0)


class TestActivityNotificationTask(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = VerifiedUserFactory()
        cls.other_user = VerifiedUserFactory()
        cls.non_verified_user = UserFactory()
        cls.group = GroupFactory(members=[cls.user, cls.other_user, cls.non_verified_user])
        cls.place = PlaceFactory(group=cls.group, subscribers=[cls.user, cls.other_user, cls.non_verified_user])

        cls.declined_place = PlaceFactory(group=cls.group, status=PlaceStatus.DECLINED.value)

        # unsubscribe other_user from notifications
        GroupMembership.objects.filter(group=cls.group, user=cls.other_user).update(notification_types=[])

        # add some random inactive users, to make sure we don't send to them
        inactive_users = [VerifiedUserFactory(language="en") for _ in list(range(randint(2, 5)))]
        for user in inactive_users:
            membership = cls.group.add_member(user)
            membership.inactive_at = timezone.now()
            membership.save()

    def setUp(self):
        mail.outbox = []

    def create_user(self, roles):
        user = VerifiedUserFactory()
        self.group.add_member(user)
        PlaceSubscription.objects.create(place=self.place, user=user)
        GroupMembership.objects.filter(group=self.group, user=user).update(roles=roles)
        return user

    def create_empty_activity(self, delta, place=None, **kwargs):
        if place is None:
            place = self.place
        return ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            **kwargs,
        )

    def create_not_full_activity(self, delta, place=None):
        if place is None:
            place = self.place
        activity = ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
        )
        activity.add_participant(self.other_user)
        activity.save()
        return activity

    def create_user_activity(self, delta, place=None, **kwargs):
        if place is None:
            place = self.place
        activity = ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            **kwargs,
        )
        activity.add_participant(self.user)
        activity.save()
        return activity

    def create_deleted_activity(self, delta, place=None):
        if place is None:
            place = self.place
        return ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            deleted=True,
        )

    def create_disabled_activity(self, delta, place=None):
        if place is None:
            place = self.place
        return ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            is_disabled=True,
        )

    def test_user_activities(self):
        with group_timezone_at(self.group, hour=20):
            user_activity_tonight = self.create_user_activity(relativedelta(minutes=50))
            user_activity_tomorrow = self.create_user_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]["tonight_user"]), [user_activity_tonight])
            self.assertEqual(list(entries[0]["tomorrow_user"]), [user_activity_tomorrow])

    def test_empty_activities(self):
        with group_timezone_at(self.group, hour=20):
            empty_activity_tonight = self.create_empty_activity(relativedelta(minutes=50))
            empty_activity_tomorrow = self.create_empty_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]["tonight_empty"]), [empty_activity_tonight])
            self.assertEqual(list(entries[0]["tomorrow_empty"]), [empty_activity_tomorrow])

    def test_not_full_activities(self):
        with group_timezone_at(self.group, hour=20):
            not_full_activity_tonight = self.create_not_full_activity(relativedelta(minutes=50))
            not_full_activity_tomorrow = self.create_not_full_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]["tonight_not_full"]), [not_full_activity_tonight])
            self.assertEqual(list(entries[0]["tomorrow_not_full"]), [not_full_activity_tomorrow])

    def test_do_not_include_not_full_if_user_is_participant(self):
        with group_timezone_at(self.group, hour=20):
            self.create_user_activity(relativedelta(minutes=50))
            self.create_user_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]["tonight_not_full"]), [])
            self.assertEqual(list(entries[0]["tomorrow_not_full"]), [])

    def test_considers_participant_types(self):
        with group_timezone_at(self.group, hour=20):
            approved_user = self.create_user(roles=[GROUP_MEMBER, GROUP_EDITOR, APPROVED])
            anyone_activity = self.create_empty_activity(relativedelta(minutes=30))
            approved_activity = self.create_empty_activity(
                relativedelta(minutes=50),
                participant_types=[
                    {
                        "role": APPROVED,
                        "max_participants": 3,
                    }
                ],
            )
            entries = fetch_activity_notification_data_for_group(self.group)

            def entries_for(user, key):
                for entry in entries:
                    if entry["user"] == user:
                        return list(entry[key])

            self.assertEqual(entries_for(self.user, "tonight_empty"), [anyone_activity])
            self.assertEqual(entries_for(approved_user, "tonight_empty"), [anyone_activity, approved_activity])

    def test_send_notification_email(self):
        with group_timezone_at(self.group, hour=20):
            self.create_empty_activity(delta=relativedelta(minutes=10))
            daily_activity_notifications()
            expected_users = [self.user]
            self.assertEqual(len(mail.outbox), len(expected_users))
            self.assertEqual(set(email for m in mail.outbox for email in m.to), set(u.email for u in expected_users))
            self.assertIn(place_url(self.place), mail.outbox[0].body)

    def test_does_not_send_if_no_activities(self):
        with group_timezone_at(self.group, hour=20):
            daily_activity_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_at_other_times(self):
        with group_timezone_at(self.group, hour=21):
            self.create_empty_activity(delta=relativedelta(minutes=10))
            daily_activity_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_ignores_not_active_places(self):
        with group_timezone_at(self.group, hour=20):
            self.create_empty_activity(delta=relativedelta(minutes=10), place=self.declined_place)
            daily_activity_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_ignores_disabled_activities(self):
        with group_timezone_at(self.group, hour=20):
            self.create_disabled_activity(delta=relativedelta(minutes=10))
            daily_activity_notifications()
            self.assertEqual(len(mail.outbox), 0)

    @patch("karrot.activities.stats.write_points")
    def test_writes_stats(self, write_points):
        write_points()
        with group_timezone_at(self.group, hour=20):
            tonight = relativedelta(minutes=10)
            tomorrow = relativedelta(hours=10)
            [self.create_user_activity(tonight) for _ in range(2)]
            [self.create_empty_activity(tonight) for _ in range(3)]
            [self.create_not_full_activity(tonight) for _ in range(4)]
            [self.create_user_activity(tomorrow) for _ in range(5)]
            [self.create_empty_activity(tomorrow) for _ in range(6)]
            [self.create_not_full_activity(tomorrow) for _ in range(7)]
            daily_activity_notifications()
            write_points.assert_called_with(
                [
                    {
                        "measurement": "karrot.email.activity_notification",
                        "tags": {
                            "group": str(self.group.id),
                            "group_status": self.group.status,
                        },
                        "fields": {
                            "value": 1,
                            "tonight_user": 2,
                            "tonight_empty": 3,
                            "tonight_not_full": 4,
                            "tomorrow_user": 5,
                            "tomorrow_empty": 6,
                            "tomorrow_not_full": 7,
                        },
                    }
                ]
            )
