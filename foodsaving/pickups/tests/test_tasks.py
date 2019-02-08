from contextlib import contextmanager
from random import randint
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.pickups.models import PickupDate, to_range
from foodsaving.pickups.tasks import daily_pickup_notifications, fetch_pickup_notification_data_for_group
from foodsaving.places.factories import PlaceFactory
from foodsaving.places.models import PlaceStatus
from foodsaving.users.factories import VerifiedUserFactory, UserFactory
from foodsaving.utils.frontend_urls import place_url


@contextmanager
def group_timezone_at(group, **kwargs):
    with timezone.override(group.timezone):
        datetime = timezone.localtime(timezone=group.timezone).replace(**kwargs)
        with freeze_time(datetime, tick=True):
            yield


class TestPickupNotificationTask(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.other_user = VerifiedUserFactory()
        self.non_verified_user = UserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user, self.non_verified_user])
        self.place = PlaceFactory(group=self.group)

        self.declined_place = PlaceFactory(group=self.group, status=PlaceStatus.DECLINED.value)

        # unsubscribe other_user from notifications
        GroupMembership.objects.filter(group=self.group, user=self.other_user).update(notification_types=[])

        # add some random inactive users, to make sure we don't send to them
        inactive_users = [VerifiedUserFactory(language='en') for _ in list(range(randint(2, 5)))]
        for user in inactive_users:
            membership = self.group.add_member(user)
            membership.inactive_at = timezone.now()
            membership.save()

        mail.outbox = []

    def create_empty_pickup(self, delta, place=None):
        if place is None:
            place = self.place
        return PickupDate.objects.create(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_collectors=1,
        )

    def create_not_full_pickup(self, delta, place=None):
        if place is None:
            place = self.place
        pickup = PickupDate.objects.create(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_collectors=2,
        )
        pickup.add_collector(self.other_user)
        pickup.save()
        return pickup

    def create_user_pickup(self, delta, place=None, **kwargs):
        if place is None:
            place = self.place
        pickup = PickupDate.objects.create(
            place=place,
            date=to_range(timezone.localtime() + delta),
            **kwargs,
        )
        pickup.add_collector(self.user)
        pickup.save()
        return pickup

    def create_deleted_pickup(self, delta, place=None):
        if place is None:
            place = self.place
        return PickupDate.objects.create(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_collectors=1,
            deleted=True,
        )

    def create_disabled_pickup(self, delta, place=None):
        if place is None:
            place = self.place
        return PickupDate.objects.create(
            place=place,
            date=to_range(timezone.localtime() + delta),
            max_collectors=1,
            is_disabled=True,
        )

    def test_user_pickups(self):
        with group_timezone_at(self.group, hour=20):
            user_pickup_tonight = self.create_user_pickup(relativedelta(minutes=50), max_collectors=1)
            user_pickup_tomorrow = self.create_user_pickup(relativedelta(hours=8), max_collectors=1)
            entries = fetch_pickup_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_user']), [user_pickup_tonight])
            self.assertEqual(list(entries[0]['tomorrow_user']), [user_pickup_tomorrow])

    def test_empty_pickups(self):
        with group_timezone_at(self.group, hour=20):
            empty_pickup_tonight = self.create_empty_pickup(relativedelta(minutes=50))
            empty_pickup_tomorrow = self.create_empty_pickup(relativedelta(hours=8))
            entries = fetch_pickup_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_empty']), [empty_pickup_tonight])
            self.assertEqual(list(entries[0]['tomorrow_empty']), [empty_pickup_tomorrow])

    def test_not_full_pickups(self):
        with group_timezone_at(self.group, hour=20):
            not_full_pickup_tonight = self.create_not_full_pickup(relativedelta(minutes=50))
            not_full_pickup_tomorrow = self.create_not_full_pickup(relativedelta(hours=8))
            entries = fetch_pickup_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_not_full']), [not_full_pickup_tonight])
            self.assertEqual(list(entries[0]['tomorrow_not_full']), [not_full_pickup_tomorrow])

    def test_do_not_include_not_full_if_user_is_collector(self):
        with group_timezone_at(self.group, hour=20):
            self.create_user_pickup(relativedelta(minutes=50), max_collectors=2)
            self.create_user_pickup(relativedelta(hours=8), max_collectors=2)
            entries = fetch_pickup_notification_data_for_group(self.group)
            self.assertEqual(list(entries[0]['tonight_not_full']), [])
            self.assertEqual(list(entries[0]['tomorrow_not_full']), [])

    def test_send_notification_email(self):
        with group_timezone_at(self.group, hour=20):
            self.create_empty_pickup(delta=relativedelta(minutes=10))
            daily_pickup_notifications()
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(place_url(self.place), mail.outbox[0].body)

    def test_does_not_send_if_no_pickups(self):
        with group_timezone_at(self.group, hour=20):
            daily_pickup_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_at_other_times(self):
        with group_timezone_at(self.group, hour=21):
            self.create_empty_pickup(delta=relativedelta(minutes=10))
            daily_pickup_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_ignores_not_active_places(self):
        with group_timezone_at(self.group, hour=20):
            self.create_empty_pickup(delta=relativedelta(minutes=10), place=self.declined_place)
            daily_pickup_notifications()
            self.assertEqual(len(mail.outbox), 0)

    def test_ignores_disabled_pickups(self):
        with group_timezone_at(self.group, hour=20):
            self.create_disabled_pickup(delta=relativedelta(minutes=10))
            daily_pickup_notifications()
            self.assertEqual(len(mail.outbox), 0)

    @patch('foodsaving.pickups.stats.write_points')
    def test_writes_stats(self, write_points):
        write_points()
        with group_timezone_at(self.group, hour=20):
            tonight = relativedelta(minutes=10)
            tomorrow = relativedelta(hours=10)
            [self.create_user_pickup(tonight) for _ in range(2)]
            [self.create_empty_pickup(tonight) for _ in range(3)]
            [self.create_not_full_pickup(tonight) for _ in range(4)]
            [self.create_user_pickup(tomorrow) for _ in range(5)]
            [self.create_empty_pickup(tomorrow) for _ in range(6)]
            [self.create_not_full_pickup(tomorrow) for _ in range(7)]
            daily_pickup_notifications()
            write_points.assert_called_with([{
                'measurement': 'karrot.email.pickup_notification',
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
