from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups import stats
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestGroupStats(TestCase):

    @patch('foodsaving.groups.stats.write_points')
    def test_group_members_stats_foo(self, mock_write_points):
        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        members = [UserFactory() for _ in range(10)]
        group = GroupFactory(members=members)

        update_member_activity(members[0], days=2)
        update_member_activity(members[1], days=8)
        update_member_activity(members[2], days=31)

        stats.group_members_stats(group)

        mock_write_points.assert_called_with([{
            'measurement': 'karrot.group.members',
            'tags': {
                'group': str(group.id),
            },
            'fields': {
                'count_active_1d': 7,
                'count_active_7d': 8,
                'count_active_30d': 9,
                'count_total': 10,
            },
        }])

    @patch('foodsaving.groups.stats.write_points')
    def test_group_stores_stats(self, mock_write_points):
        group = GroupFactory()

        [StoreFactory(group=group, status='active') for _ in range(3)]
        [StoreFactory(group=group, status='negotiating') for _ in range(7)]
        [StoreFactory(group=group, status='archived') for _ in range(10)]

        stats.group_stores_stats(group)

        mock_write_points.assert_called_with([{
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
