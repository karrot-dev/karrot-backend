from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups.factories import GroupFactory
from foodsaving.notifications import tasks
from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.notifications.tasks import create_pickup_upcoming_notifications
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.pickups.models import PickupDateCollector
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestDeleteExpiredTask(TestCase):
    def test_deletes_expired_notification(self):
        one_hour_ago = timezone.now() - relativedelta(hours=1)
        group = GroupFactory()
        Notification.objects.create(
            type=NotificationType.PICKUP_UPCOMING.value,
            user=UserFactory(),
            expires_at=one_hour_ago,
            context={
                'group': group.id,
            }
        )

        tasks.delete_expired_notifications.call_local()

        self.assertEqual(Notification.objects.count(), 0)

    def test_does_not_delete_active_notifications(self):
        in_one_hour = timezone.now() + relativedelta(hours=1)
        group = GroupFactory()
        Notification.objects.create(
            type=NotificationType.PICKUP_UPCOMING.value,
            user=UserFactory(),
            expires_at=in_one_hour,
            context={
                'group': group.id,
            }
        )

        tasks.delete_expired_notifications.call_local()

        self.assertEqual(Notification.objects.count(), 1)


class TestPickupUpcomingTask(TestCase):
    def test_create_pickup_upcoming_notifications(self):
        users = [UserFactory() for _ in range(3)]
        group = GroupFactory(members=users)
        store = StoreFactory(group=group)
        in_one_hour = timezone.now() + relativedelta(hours=1)
        pickup1 = PickupDateFactory(store=store, date=in_one_hour, collectors=users)
        in_two_hours = timezone.now() + relativedelta(hours=1)
        PickupDateFactory(store=store, date=in_two_hours, collectors=users)
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(notifications.count(), 6)
        self.assertEqual(set(n.user.id for n in notifications), set(user.id for user in users))
        pickup1_user1_collector = PickupDateCollector.objects.get(user=users[0], pickupdate=pickup1)
        pickup1_user1_notification = next(
            n for n in notifications if n.context['pickup_collector'] == pickup1_user1_collector.id
        )
        self.assertEqual(
            pickup1_user1_notification.context, {
                'group': group.id,
                'store': store.id,
                'pickup': pickup1.id,
                'pickup_collector': pickup1_user1_collector.id,
            }
        )
        self.assertEqual(pickup1_user1_notification.expires_at, pickup1.date)

    def test_creates_only_one_pickup_upcoming_notification(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        store = StoreFactory(group=group)
        in_one_hour = timezone.now() + relativedelta(hours=1)
        PickupDateFactory(store=store, date=in_one_hour, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        create_pickup_upcoming_notifications.call_local()
        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(notifications.count(), 1)

    def test_creates_no_pickup_upcoming_notification_when_too_far_in_future(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        store = StoreFactory(group=group)
        in_one_day = timezone.now() + relativedelta(days=1)
        PickupDateFactory(store=store, date=in_one_day, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(notifications.count(), 0)

    def test_creates_no_pickup_upcoming_notification_when_in_past(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        store = StoreFactory(group=group)
        one_hour_ago = timezone.now() - relativedelta(hours=1)
        PickupDateFactory(store=store, date=one_hour_ago, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(notifications.count(), 0)
