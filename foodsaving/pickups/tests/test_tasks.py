from contextlib import contextmanager

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.models import PickupDate
from foodsaving.pickups.tasks import daily_pickup_notifications, fetch_pickup_notification_data_for_group
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import VerifiedUserFactory
from foodsaving.utils.email_utils import store_url


@contextmanager
def group_timezone_at(group, **kwargs):
    with timezone.override(group.timezone):
        eight_pm = timezone.localtime(timezone=group.timezone).replace(**kwargs)
        with freeze_time(eight_pm, tick=True):
            yield


class TestPickupNotificationTask(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user])
        self.store = StoreFactory(group=self.group)
        mail.outbox = []

    def test_empty_pickup(self):
        with group_timezone_at(self.group, hour=20):
            empty_pickup = PickupDate.objects.create(
                store=self.store,
                date=timezone.localtime() + relativedelta(minutes=50),
                max_collectors=10,
            )
            data = fetch_pickup_notification_data_for_group(self.group)
            self.assertEqual(len(data), 1)
            self.assertEqual(len(data[0]['tonight_empty']), 1)
            self.assertEqual(data[0]['tonight_empty'].first().id, empty_pickup.id)

    def test_send_notification_email(self):
        with group_timezone_at(self.group, hour=20):
            PickupDate.objects.create(
                store=self.store,
                date=timezone.localtime() + relativedelta(minutes=10),
                max_collectors=10,
            )

            daily_pickup_notifications()

            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(store_url(self.store), mail.outbox[0].body)
