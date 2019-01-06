from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.users import stats
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.webhooks.models import EmailEvent


class TestUserStats(TestCase):
    def test_user_stats(self):
        self.maxDiff = None

        def do_pickup(store, user, **kwargs):
            pickup = PickupDateFactory(store=store, date=timezone.now() - relativedelta(**kwargs))
            pickup.add_collector(user)

        # 9 verified users, 1 unverified user
        users = [VerifiedUserFactory() for _ in range(9)]
        users.insert(0, UserFactory())

        # 5 fully inactive users (only in one group and marked as inactive in that group)
        inactive_users = [VerifiedUserFactory() for _ in range(5)]
        inactive_group = GroupFactory(members=inactive_users)
        GroupMembership.objects.filter(group=inactive_group).update(inactive_at=timezone.now())

        # 1 deleted user
        deleted_user = UserFactory()
        deleted_user.deleted = True
        deleted_user.save()

        # one user with bounced email
        bounce_user = users[0]
        for _ in range(5):
            EmailEvent.objects.create(created_at=timezone.now(), address=bounce_user.email, event='bounce', payload={})

        # one user with location
        location_user = users[1]
        location_user.latitude = 50.4
        location_user.longitude = 23.2
        location_user.save()

        # one user with mobile number
        mobile_number_user = users[2]
        mobile_number_user.mobile_number = '123'
        mobile_number_user.save()

        # five users without description
        def remove_description(user):
            user.description = ''
            user.save()

        [remove_description(u) for u in users[:5]]

        # one user with photo
        photo_user = users[4]
        photo_user.photo = 'photo.jpg'
        photo_user.save()

        # 2 groups where everybody is active, 1 where everybody is inactive
        group = GroupFactory(members=users[:9])
        GroupFactory(members=users[:9])
        group_all_inactive = GroupFactory(members=users[:9])
        GroupMembership.objects.filter(group=group_all_inactive).update(inactive_at=timezone.now())

        # 1 active user that did a pickup
        store = StoreFactory(group=group)
        do_pickup(store, users[0], days=10)

        # 2 inactive user that did a pickup long ago
        inactive_store = StoreFactory(group=inactive_group)
        do_pickup(inactive_store, inactive_users[0], days=60)
        do_pickup(inactive_store, inactive_users[1], days=90)

        points = stats.get_users_stats()

        self.assertEqual(
            points, {
                'active_count': 9,
                'active_unverified_count': 1,
                'active_ignored_email_count': 1,
                'active_with_location_count': 1,
                'active_with_mobile_number_count': 1,
                'active_with_description_count': 4,
                'active_with_photo_count': 1,
                'active_memberships_per_active_user_avg': 2.0,
                'no_membership_count': 1,
                'deleted_count': 1,
                'pickup_active_count': 1,
                'pickup_count': 3,
            }
        )
