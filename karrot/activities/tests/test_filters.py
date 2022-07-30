from collections import namedtuple
from datetime import timedelta
from django.db import DataError
from django.test import TestCase
from django.utils import timezone

from karrot.activities.factories import ActivityFactory
from karrot.groups.factories import GroupFactory
from karrot.activities.filters import ActivitiesFilter
from karrot.activities.models import Activity
from karrot.places.factories import PlaceFactory
from karrot.places.models import PlaceSubscription
from karrot.users.factories import VerifiedUserFactory

MockRequest = namedtuple('Request', ['user'])


def halfway_datetime(range):
    return range.lower + timedelta(seconds=((range.upper - range.lower).seconds / 2))


class TestActivityFilters(TestCase):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.other_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.other_member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, max_participants=2)

    def test_with_no_parameters(self):
        qs = Activity.objects.filter(place=self.place)
        f = ActivitiesFilter(data={}, queryset=qs)
        self.assertEqual(list(f.qs), [self.activity])

    def expect_results(
        self,
        date_min=None,
        date_max=None,
        activity_type=None,
        slots=None,
        places=None,
        user=None,
        results=None,
    ):
        qs = Activity.objects.filter(place=self.place)
        f = ActivitiesFilter(
            data={
                'date_min': date_min,
                'date_max': date_max,
                'activity_type': activity_type,
                'slots': slots,
                'places': places,
            },
            queryset=qs,
            request=MockRequest(user=user)
        )
        self.assertEqual(list(f.qs), results)

    def test_with_date_min_before_activity(self):
        now = timezone.now()
        self.expect_results(
            date_min=now - timedelta(hours=1),
            results=[self.activity],
        )

    def test_with_date_min_during_activity(self):
        self.expect_results(
            date_min=halfway_datetime(self.activity.date),
            results=[self.activity],
        )

    def test_no_results_with_date_min_at_activity_end(self):
        self.expect_results(
            date_min=self.activity.date.end,
            results=[],
        )

    def test_with_date_max_during_activity(self):
        self.expect_results(
            date_max=halfway_datetime(self.activity.date),
            results=[self.activity],
        )

    def test_with_date_max_after_activity(self):
        self.expect_results(
            date_max=self.activity.date.end + timedelta(hours=2),
            results=[self.activity],
        )

    def test_no_results_with_date_max_before_activity(self):
        self.expect_results(
            date_max=self.activity.date.start - timedelta(hours=2),
            results=[],
        )

    def test_no_results_with_date_max_at_activity_start(self):
        self.expect_results(
            date_max=self.activity.date.start,
            results=[],
        )

    def test_with_date_max_and_min_during_activity(self):
        self.expect_results(
            date_min=self.activity.date.start + timedelta(seconds=5),
            date_max=self.activity.date.end - timedelta(seconds=5),
            results=[self.activity],
        )

    def test_with_date_max_and_min_overlapping_activity_start(self):
        self.expect_results(
            date_min=self.activity.date.start - timedelta(seconds=5),
            date_max=self.activity.date.start + timedelta(seconds=5),
            results=[self.activity],
        )

    def test_with_date_max_and_min_overlapping_activity_end(self):
        self.expect_results(
            date_min=self.activity.date.end - timedelta(seconds=5),
            date_max=self.activity.date.end + timedelta(seconds=5),
            results=[self.activity],
        )

    def test_with_date_max_and_min_containing_activity(self):
        self.expect_results(
            date_min=self.activity.date.start - timedelta(seconds=5),
            date_max=self.activity.date.end + timedelta(seconds=5),
            results=[self.activity],
        )

    def test_fails_if_date_max_less_than_date_min(self):
        now = timezone.now()
        qs = Activity.objects.filter(place=self.place)
        with self.assertRaises(DataError):
            list(ActivitiesFilter(data={
                'date_min': now,
                'date_max': now - timedelta(hours=1),
            }, queryset=qs).qs)

    def test_with_activity_type(self):
        self.expect_results(
            activity_type=self.activity.activity_type.id,
            results=[self.activity],
        )

    def test_with_other_activity_type(self):
        other_activity_type = self.group.activity_types.exclude(id=self.activity.activity_type_id).first()
        self.expect_results(
            activity_type=other_activity_type.id,
            results=[],
        )

    def test_with_slots_free(self):
        self.expect_results(
            slots='free',
            results=[self.activity],
        )
        self.activity.add_participant(self.member)
        self.expect_results(
            slots='free',
            results=[self.activity],
        )
        self.activity.add_participant(self.other_member)
        self.expect_results(
            slots='free',
            results=[],
        )

    def test_with_slots_empty(self):
        self.expect_results(
            slots='empty',
            results=[self.activity],
        )
        self.activity.add_participant(self.member)
        self.expect_results(
            slots='empty',
            results=[],
        )
        self.activity.add_participant(self.other_member)
        self.expect_results(
            slots='empty',
            results=[],
        )

    def test_with_slots_joined(self):
        self.expect_results(
            user=self.member,
            slots='joined',
            results=[],
        )
        self.activity.add_participant(self.member)
        self.expect_results(
            user=self.member,
            slots='joined',
            results=[self.activity],
        )
        self.expect_results(
            user=self.other_member,
            slots='joined',
            results=[],
        )

    def test_with_subscribed_places(self):
        self.expect_results(
            user=self.member,
            places='subscribed',
            results=[],
        )
        PlaceSubscription.objects.create(place=self.place, user=self.member)
        self.expect_results(
            user=self.member,
            places='subscribed',
            results=[self.activity],
        )
