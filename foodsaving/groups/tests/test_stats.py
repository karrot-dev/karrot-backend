from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups import stats
from foodsaving.groups.factories import GroupFactory, GroupApplicationFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestGroupStats(TestCase):

    def test_group_members_stats_foo(self):
        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        members = [UserFactory() for _ in range(10)]
        group = GroupFactory(members=members)

        update_member_activity(members[0], days=2)
        update_member_activity(members[1], days=8)
        update_member_activity(members[2], days=31)
        update_member_activity(members[3], days=61)
        update_member_activity(members[4], days=91)

        points = stats.get_group_members_stats(group)

        self.assertEqual(points, [{
            'measurement': 'karrot.group.members',
            'tags': {
                'group': str(group.id),
            },
            'fields': {
                'count_active_1d': 5,
                'count_active_7d': 6,
                'count_active_30d': 7,
                'count_active_60d': 8,
                'count_active_90d': 9,
                'count_total': 10,
            },
        }])

    def test_group_stores_stats(self):
        group = GroupFactory()

        [StoreFactory(group=group, status='active') for _ in range(3)]
        [StoreFactory(group=group, status='negotiating') for _ in range(7)]
        [StoreFactory(group=group, status='archived') for _ in range(10)]

        points = stats.get_group_stores_stats(group)

        self.assertEqual(points, [{
            'measurement': 'karrot.group.stores',
            'tags': {
                'group': str(group.id),
            },
            'fields': {
                'count_total': 20,
                'count_status_active': 3,
                'count_status_negotiating': 7,
                'count_status_archived': 10,
            },
        }])

    def test_group_application_stats(self):
        group = GroupFactory()

        [GroupApplicationFactory(group=group, user=UserFactory(), status='pending') for _ in range(3)]
        [GroupApplicationFactory(group=group, user=UserFactory(), status='accepted') for _ in range(4)]
        [GroupApplicationFactory(group=group, user=UserFactory(), status='declined') for _ in range(5)]
        [GroupApplicationFactory(group=group, user=UserFactory(), status='withdrawn') for _ in range(6)]

        points = stats.get_group_application_stats(group)

        self.assertEqual(points, [{
            'measurement': 'karrot.group.applications',
            'tags': {
                'group': str(group.id),
            },
            'fields': {
                'count_total': 18,
                'count_status_pending': 3,
                'count_status_accepted': 4,
                'count_status_declined': 5,
                'count_status_withdrawn': 6,
            },
        }])

    @patch('foodsaving.groups.stats.write_points')
    def test_group_application_status_update(self, write_points):
        two_hours_ago = timezone.now() - relativedelta(hours=2)
        application = GroupApplicationFactory(group=GroupFactory(), user=UserFactory(), created_at=two_hours_ago)
        application.status = 'accepted'
        application.save()

        write_points.reset_mock()
        stats.application_status_update(application)
        write_points.assert_called_with([{
            'measurement': 'karrot.events',
            'tags': {
                'group': str(application.group.id)
            },
            'fields': {
                'application_accepted': 1,
                'application_accepted_seconds': 60 * 60 * 2,
            },
        }])
