from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups import stats, roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestGroupStats(TestCase):
    def test_group_members_stats(self):
        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        def do_pickup(user, **kwargs):
            pickup = PickupDateFactory(store=store, date=timezone.now() - relativedelta(**kwargs))
            pickup.add_collector(user)

        def set_as_newcomer(user):
            membership = GroupMembership.objects.filter(user=user).first()
            membership.remove_roles([roles.GROUP_EDITOR])
            membership.save()

        members = [UserFactory() for _ in range(10)]
        group = GroupFactory(members=members)
        store = StoreFactory(group=group)

        set_as_newcomer(members[0])
        update_member_activity(members[0], days=2)
        update_member_activity(members[1], days=8)
        update_member_activity(members[2], days=31)
        update_member_activity(members[3], days=61)
        update_member_activity(members[4], days=91)

        do_pickup(members[0], days=2)
        do_pickup(members[1], days=8)
        do_pickup(members[2], days=31)
        do_pickup(members[3], days=61)
        do_pickup(members[4], days=91)

        points = stats.get_group_members_stats(group)

        self.assertEqual(
            points, [{
                'measurement': 'karrot.group.members',
                'tags': {
                    'group': str(group.id),
                    'group_status': 'active',
                },
                'fields': {
                    'count_active_1d': 5,
                    'count_active_7d': 6,
                    'count_active_30d': 7,
                    'count_active_60d': 8,
                    'count_active_90d': 9,
                    'count_active_editors_1d': 5,
                    'count_active_editors_7d': 5,
                    'count_active_editors_30d': 6,
                    'count_active_editors_60d': 7,
                    'count_active_editors_90d': 8,
                    'count_active_newcomers_1d': 0,
                    'count_active_newcomers_7d': 1,
                    'count_active_newcomers_30d': 1,
                    'count_active_newcomers_60d': 1,
                    'count_active_newcomers_90d': 1,
                    'count_pickup_active_1d': 0,
                    'count_pickup_active_7d': 1,
                    'count_pickup_active_30d': 2,
                    'count_pickup_active_60d': 3,
                    'count_pickup_active_90d': 4,
                    'count_pickup_active_editors_1d': 0,
                    'count_pickup_active_editors_7d': 0,
                    'count_pickup_active_editors_30d': 1,
                    'count_pickup_active_editors_60d': 2,
                    'count_pickup_active_editors_90d': 3,
                    'count_pickup_active_newcomers_1d': 0,
                    'count_pickup_active_newcomers_7d': 1,
                    'count_pickup_active_newcomers_30d': 1,
                    'count_pickup_active_newcomers_60d': 1,
                    'count_pickup_active_newcomers_90d': 1,
                    'count_total': 10,
                    'count_editors_total': 9,
                    'count_newcomers_total': 1,
                },
            }]
        )

    def test_group_stores_stats(self):
        group = GroupFactory()

        [StoreFactory(group=group, status='active') for _ in range(3)]
        [StoreFactory(group=group, status='negotiating') for _ in range(7)]
        [StoreFactory(group=group, status='archived') for _ in range(10)]

        points = stats.get_group_stores_stats(group)

        self.assertEqual(
            points, [{
                'measurement': 'karrot.group.stores',
                'tags': {
                    'group': str(group.id),
                    'group_status': 'active',
                },
                'fields': {
                    'count_total': 20,
                    'count_status_active': 3,
                    'count_status_negotiating': 7,
                    'count_status_archived': 10,
                },
            }]
        )
