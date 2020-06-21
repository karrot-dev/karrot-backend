from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from karrot.issues.factories import (
    IssueFactory,
    fast_forward_just_before_voting_expiration,
    vote_for_further_discussion,
)
from karrot.groups.factories import GroupFactory
from karrot.notifications import tasks
from karrot.notifications.models import Notification, NotificationType
from karrot.notifications.tasks import (
    create_pickup_upcoming_notifications,
    create_voting_ends_soon_notifications,
)
from karrot.pickups.factories import PickupDateFactory
from karrot.pickups.models import PickupDateCollector, to_range
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestDeleteExpiredTask(TestCase):
    def test_deletes_expired_notification(self):
        one_hour_ago = timezone.now() - relativedelta(hours=1)
        group = GroupFactory()
        Notification.objects.create(
            type=NotificationType.PICKUP_UPCOMING.value,
            user=UserFactory(),
            expires_at=one_hour_ago,
            context={"group": group.id,},
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
            context={"group": group.id,},
        )

        tasks.delete_expired_notifications.call_local()

        self.assertEqual(Notification.objects.count(), 1)


class TestPickupUpcomingTask(TestCase):
    def test_create_pickup_upcoming_notifications(self):
        users = [UserFactory() for _ in range(3)]
        group = GroupFactory(members=users)
        place = PlaceFactory(group=group)
        in_one_hour = to_range(timezone.now() + relativedelta(hours=1))
        pickup1 = PickupDateFactory(place=place, date=in_one_hour, collectors=users)
        in_two_hours = to_range(timezone.now() + relativedelta(hours=1))
        PickupDateFactory(place=place, date=in_two_hours, collectors=users)
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(
            type=NotificationType.PICKUP_UPCOMING.value
        )
        self.assertEqual(notifications.count(), 6)
        self.assertEqual(
            set(n.user.id for n in notifications), set(user.id for user in users)
        )
        pickup1_user1_collector = PickupDateCollector.objects.get(
            user=users[0], pickupdate=pickup1
        )
        pickup1_user1_notification = next(
            n
            for n in notifications
            if n.context["pickup_collector"] == pickup1_user1_collector.id
        )
        self.assertEqual(
            pickup1_user1_notification.context,
            {
                "group": group.id,
                "place": place.id,
                "pickup": pickup1.id,
                "pickup_collector": pickup1_user1_collector.id,
            },
        )
        self.assertEqual(pickup1_user1_notification.expires_at, pickup1.date.start)

    def test_creates_only_one_pickup_upcoming_notification(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        in_one_hour = to_range(timezone.now() + relativedelta(hours=1))
        PickupDateFactory(place=place, date=in_one_hour, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        create_pickup_upcoming_notifications.call_local()
        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(
            type=NotificationType.PICKUP_UPCOMING.value
        )
        self.assertEqual(notifications.count(), 1)

    def test_creates_no_pickup_upcoming_notification_when_too_far_in_future(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        in_one_day = to_range(timezone.now() + relativedelta(days=1))
        PickupDateFactory(place=place, date=in_one_day, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(
            type=NotificationType.PICKUP_UPCOMING.value
        )
        self.assertEqual(notifications.count(), 0)

    def test_creates_no_pickup_upcoming_notification_when_in_past(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        one_hour_ago = to_range(timezone.now() - relativedelta(hours=1))
        PickupDateFactory(place=place, date=one_hour_ago, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        notifications = Notification.objects.filter(
            type=NotificationType.PICKUP_UPCOMING.value
        )
        self.assertEqual(notifications.count(), 0)


class TestVotingEndsSoonTask(TestCase):
    def test_create_voting_ends_soon_notifications(self):
        creator, affected_user, voter = UserFactory(), UserFactory(), UserFactory()
        group = GroupFactory(members=[creator, affected_user, voter])
        issue = IssueFactory(
            group=group, created_by=creator, affected_user=affected_user
        )
        voting = issue.latest_voting()
        # let's vote with user "voter"
        vote_for_further_discussion(voting=voting, user=voter)
        Notification.objects.all().delete()

        with fast_forward_just_before_voting_expiration(voting):
            create_voting_ends_soon_notifications()
            # can call it a second time without duplicating notifications
            create_voting_ends_soon_notifications()

        notifications = Notification.objects.filter(
            type=NotificationType.VOTING_ENDS_SOON.value
        )
        # user "voter" is not being notified
        self.assertEqual(
            sorted([n.user_id for n in notifications]),
            sorted([issue.affected_user_id, issue.created_by_id]),
        )
