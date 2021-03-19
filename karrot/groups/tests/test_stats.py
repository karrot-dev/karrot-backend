from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from karrot.groups import stats, roles
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestGroupStats(TestCase):
    def test_group_members_stats(self):
        def update_member_activity(user, **kwargs):
            GroupMembership.objects.filter(user=user).update(lastseen_at=timezone.now() - relativedelta(**kwargs))

        def do_activity(user, **kwargs):
            activity = ActivityFactory(place=place, date=to_range(timezone.now() - relativedelta(**kwargs)))
            activity.add_participant(user)

        def set_as_newcomer(user):
            membership = GroupMembership.objects.filter(user=user).first()
            membership.remove_roles([roles.GROUP_EDITOR])
            membership.save()

        members = [UserFactory() for _ in range(10)]
        group = GroupFactory(members=members)
        place = PlaceFactory(group=group)

        set_as_newcomer(members[0])
        update_member_activity(members[0], days=2)
        update_member_activity(members[1], days=8)
        update_member_activity(members[2], days=31)
        update_member_activity(members[3], days=61)
        update_member_activity(members[4], days=91)

        do_activity(members[0], days=2)
        do_activity(members[1], days=8)
        do_activity(members[2], days=31)
        do_activity(members[3], days=61)
        do_activity(members[4], days=91)

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
                    'count_activity_active_1d': 0,
                    'count_activity_active_7d': 1,
                    'count_activity_active_30d': 2,
                    'count_activity_active_60d': 3,
                    'count_activity_active_90d': 4,
                    'count_activity_active_editors_1d': 0,
                    'count_activity_active_editors_7d': 0,
                    'count_activity_active_editors_30d': 1,
                    'count_activity_active_editors_60d': 2,
                    'count_activity_active_editors_90d': 3,
                    'count_activity_active_newcomers_1d': 0,
                    'count_activity_active_newcomers_7d': 1,
                    'count_activity_active_newcomers_30d': 1,
                    'count_activity_active_newcomers_60d': 1,
                    'count_activity_active_newcomers_90d': 1,
                    'count_total': 10,
                    'count_editors_total': 9,
                    'count_newcomers_total': 1,
                    'count_active_30d_with_notification_type_weekly_summary': 7,
                    'count_active_30d_with_notification_type_new_application': 7,
                    'count_active_30d_with_notification_type_new_offer': 7,
                    'count_active_30d_with_notification_type_daily_activity_notification': 7,
                    'count_active_30d_with_notification_type_conflict_resolution': 7,
                },
            }]
        )

    def test_group_places_stats(self):
        group = GroupFactory()

        [PlaceFactory(group=group, status=group.place_statuses.get(name='Active')) for _ in range(3)]
        [PlaceFactory(group=group, status=group.place_statuses.get(name='Negotiating')) for _ in range(7)]
        [PlaceFactory(group=group, status=group.place_statuses.get(name='Archived')) for _ in range(10)]

        points = stats.get_group_places_stats(group)

        self.assertEqual(
            points, [{
                'measurement': 'karrot.group.places',
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
