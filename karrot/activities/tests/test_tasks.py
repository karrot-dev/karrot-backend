from contextlib import contextmanager
from random import randint
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APITestCase

from karrot.activities import tasks
from karrot.activities.factories import ActivityFactory
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.activities.models import ActivityParticipant, to_range
from karrot.activities.tasks import daily_activity_notifications, fetch_activity_notification_data_for_group
from karrot.places.factories import PlaceFactory
from karrot.places.models import PlaceStatusOld
from karrot.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from karrot.users.factories import VerifiedUserFactory, UserFactory
from karrot.utils.frontend_urls import place_url


@contextmanager
def group_timezone_at(group, **kwargs):
    with timezone.override(group.timezone):
        datetime = timezone.localtime(timezone=group.timezone).replace(**kwargs)
        with freeze_time(datetime, tick=True):
            yield


@patch('karrot.activities.tasks.notify_subscribers_by_device')
class TestActivityReminderTask(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.other_user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user])
        self.place = PlaceFactory(group=self.group, subscribers=[self.user, self.other_user])
        self.activity = ActivityFactory(place=self.place)
        self.subscriptions = [
            PushSubscription.objects.create(user=self.user, token='', platform=PushSubscriptionPlatform.ANDROID.value)
        ]

    def test_activity_reminder_notifies_subscribers(self, notify_subscribers_by_device):
        participant = ActivityParticipant.objects.create(user=self.user, activity=self.activity)
        notify_subscribers_by_device.reset_mock()
        tasks.activity_reminder.call_local(participant.id)
        args, kwargs = notify_subscribers_by_device.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0].first(), self.subscriptions[0])
        self.assertIn(
            f'/group/{self.group.id}/place/{self.place.id}/activities/{self.activity.id}/detail',
            kwargs['click_action'],
        )
        self.assertIn(
            'Upcoming {}'.format(self.activity.activity_type.name),
            kwargs['fcm_options']['message_title'],
        )
        self.assertIn(
            self.place.name,
            kwargs['fcm_options']['message_body'],
        )


class TestActivityNotificationTask(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = VerifiedUserFactory()
        cls.other_user = VerifiedUserFactory()
        cls.non_verified_user = UserFactory()
        cls.group = GroupFactory(members=[cls.user, cls.other_user, cls.non_verified_user])
        cls.place = PlaceFactory(group=cls.group, subscribers=[cls.user, cls.other_user, cls.non_verified_user])

        cls.declined_place = PlaceFactory(group=cls.group, status=PlaceStatusOld.DECLINED.value)

        # unsubscribe other_user from notifications
        GroupMembership.objects.filter(group=cls.group, user=cls.other_user).update(notification_types=[])

        # add some random inactive users, to make sure we don't send to them
        inactive_users = [VerifiedUserFactory(language='en') for _ in list(range(randint(2, 5)))]
        for user in inactive_users:
            membership = cls.group.add_member(user)
            membership.inactive_at = timezone.now()
            membership.save()

    def setUp(self):
        mail.outbox = []

    def create_empty_activity(self, delta, place=None):
        if place is None:
            place = self.place
        return ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_participants=1,
        )

    def create_not_full_activity(self, delta, place=None):
        if place is None:
            place = self.place
        activity = ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_participants=2,
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
            max_participants=1,
            deleted=True,
        )

    def create_disabled_activity(self, delta, place=None):
        if place is None:
            place = self.place
        return ActivityFactory(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_participants=1,
            is_disabled=True,
        )

    def test_user_activities(self):
        with group_timezone_at(self.group, hour=20):
            user_activity_tonight = self.create_user_activity(relativedelta(minutes=50), max_participants=1)
            user_activity_tomorrow = self.create_user_activity(relativedelta(hours=8), max_participants=1)
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_user']), [user_activity_tonight])
            self.assertEqual(list(entries[0]['tomorrow_user']), [user_activity_tomorrow])

    def test_empty_activities(self):
        with group_timezone_at(self.group, hour=20):
            empty_activity_tonight = self.create_empty_activity(relativedelta(minutes=50))
            empty_activity_tomorrow = self.create_empty_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_empty']), [empty_activity_tonight])
            self.assertEqual(list(entries[0]['tomorrow_empty']), [empty_activity_tomorrow])

    def test_not_full_activities(self):
        with group_timezone_at(self.group, hour=20):
            not_full_activity_tonight = self.create_not_full_activity(relativedelta(minutes=50))
            not_full_activity_tomorrow = self.create_not_full_activity(relativedelta(hours=8))
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_not_full']), [not_full_activity_tonight])
            self.assertEqual(list(entries[0]['tomorrow_not_full']), [not_full_activity_tomorrow])

    def test_do_not_include_not_full_if_user_is_participant(self):
        with group_timezone_at(self.group, hour=20):
            self.create_user_activity(relativedelta(minutes=50), max_participants=2)
            self.create_user_activity(relativedelta(hours=8), max_participants=2)
            entries = fetch_activity_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_not_full']), [])
            self.assertEqual(list(entries[0]['tomorrow_not_full']), [])

    def test_send_notification_email(self):
        with group_timezone_at(self.group, hour=20):
            self.create_empty_activity(delta=relativedelta(minutes=10))
            daily_activity_notifications()
            self.assertEqual(len(mail.outbox), 1)
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

    @patch('karrot.activities.stats.write_points')
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
            write_points.assert_called_with([{
                'measurement': 'karrot.email.activity_notification',
                'tags': {
                    'group': str(self.group.id),
                    'group_status': self.group.status,
                },
                'fields': {
                    'value': 1,
                    'tonight_user': 2,
                    'tonight_empty': 3,
                    'tonight_not_full': 4,
                    'tomorrow_user': 5,
                    'tomorrow_empty': 6,
                    'tomorrow_not_full': 7,
                }
            }])
