from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.users import stats
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.webhooks.models import EmailEvent


class TestUserStats(TestCase):
    def test_user_stats(self):
        self.maxDiff = None

        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        # 9 verified users, 1 unverified user
        users = [VerifiedUserFactory() for _ in range(9)]
        users.insert(0, UserFactory())

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

        # 3 groups
        GroupFactory(members=users[:9])
        GroupFactory(members=users[:9])
        GroupFactory(members=users[:9])
        for user in users:
            update_member_activity(user, days=5)

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
                'active_with_groups_count_avg': 3.0,
                'active_with_groups_count_stddev': 0.0,
                'without_group_count': 1,
                'deleted_count': 1,
            }
        )
