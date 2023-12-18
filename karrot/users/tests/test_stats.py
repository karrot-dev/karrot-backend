from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.places.factories import PlaceFactory
from karrot.users import stats
from karrot.users.factories import UserFactory, VerifiedUserFactory


class TestUserStats(TestCase):
    def test_user_stats(self):
        self.maxDiff = None

        # avoid test flakiness: remove leftover users from other tests (???)
        get_user_model().objects.all().delete()

        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        def do_activity(place, user, **kwargs):
            activity = ActivityFactory(place=place, date=to_range(timezone.now() - relativedelta(**kwargs)))
            activity.add_participant(user)

        # 9 verified users, 1 unverified user
        users = [VerifiedUserFactory() for _ in range(9)]
        users.insert(0, UserFactory())

        # 5 some users of varying levels of inactivity
        inactive_users = [VerifiedUserFactory() for _ in range(5)]
        inactive_group = GroupFactory(members=inactive_users)
        GroupMembership.objects.filter(group=inactive_group).update(inactive_at=timezone.now())
        update_member_activity(inactive_users[0], days=2)
        update_member_activity(inactive_users[1], days=8)
        update_member_activity(inactive_users[2], days=31)
        update_member_activity(inactive_users[3], days=61)
        update_member_activity(inactive_users[4], days=91)

        # 1 deleted user
        deleted_user = UserFactory()
        deleted_user.deleted = True
        deleted_user.save()

        # one user with location
        location_user = users[1]
        location_user.latitude = 50.4
        location_user.longitude = 23.2
        location_user.save()

        # one user with mobile number
        mobile_number_user = users[2]
        mobile_number_user.mobile_number = "123"
        mobile_number_user.save()

        # five users without description
        def remove_description(user):
            user.description = ""
            user.save()

        [remove_description(u) for u in users[:5]]

        # one user with photo
        photo_user = users[4]
        photo_user.photo = "photo.jpg"
        photo_user.save()

        # 2 groups where everybody is active, 1 where everybody is inactive
        group = GroupFactory(members=users[:9])
        GroupFactory(members=users[:9])
        group_all_inactive = GroupFactory(members=users[:9])
        GroupMembership.objects.filter(group=group_all_inactive).update(inactive_at=timezone.now())

        # do some activities!
        place = PlaceFactory(group=group)
        do_activity(place, users[0], days=2)
        do_activity(place, users[1], days=8)
        do_activity(place, users[2], days=31)
        do_activity(place, users[3], days=61)
        do_activity(place, users[4], days=91)

        points = stats.get_users_stats()

        self.assertEqual(
            points,
            {
                "active_count": 9,
                "active_unverified_count": 1,
                "active_with_location_count": 1,
                "active_with_mobile_number_count": 1,
                "active_with_description_count": 4,
                "active_with_photo_count": 1,
                "active_memberships_per_active_user_avg": 2.0,
                "no_membership_count": 1,
                "deleted_count": 1,
                "count_active_1d": 9,
                "count_active_7d": 10,
                "count_active_30d": 11,
                "count_active_60d": 12,
                "count_active_90d": 13,
                "count_activity_active_1d": 0,
                "count_activity_active_7d": 1,
                "count_activity_active_30d": 2,
                "count_activity_active_60d": 3,
                "count_activity_active_90d": 4,
            },
        )

    def test_user_stats_with_no_active_users(self):
        # avoid test flakiness: remove leftover users from other tests (???)
        get_user_model().objects.all().delete()

        points = stats.get_users_stats()

        self.assertEqual(
            points,
            {
                "active_count": 0,
                "active_unverified_count": 0,
                "active_with_location_count": 0,
                "active_with_mobile_number_count": 0,
                "active_with_description_count": 0,
                "active_with_photo_count": 0,
                "active_memberships_per_active_user_avg": 0,
                "no_membership_count": 0,
                "deleted_count": 0,
                "count_active_1d": 0,
                "count_active_7d": 0,
                "count_active_30d": 0,
                "count_active_60d": 0,
                "count_active_90d": 0,
                "count_activity_active_1d": 0,
                "count_activity_active_7d": 0,
                "count_activity_active_30d": 0,
                "count_activity_active_60d": 0,
                "count_activity_active_90d": 0,
            },
        )
