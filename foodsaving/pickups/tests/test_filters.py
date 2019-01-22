from datetime import timedelta
from django.db import DataError
from django.test import TestCase
from django.utils import timezone

from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.filters import PickupDatesFilter
from foodsaving.pickups.models import PickupDate
from foodsaving.stores.factories import StoreFactory


def halfway_datetime(range):
    return range.lower + timedelta(seconds=((range.upper - range.lower).seconds / 2))


class TestPickupDateFilters(TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.store = StoreFactory(group=self.group)

    def test_with_no_parameters(self):
        pickup = PickupDate.objects.create(store=self.store)
        qs = PickupDate.objects.filter(store=self.store)
        f = PickupDatesFilter(data={}, queryset=qs)
        self.assertEqual(list(f.qs), [pickup])

    def expect_results(self, date_min=None, date_max=None, results=None):
        qs = PickupDate.objects.filter(store=self.store)
        f = PickupDatesFilter(data={'date_min': date_min, 'date_max': date_max}, queryset=qs)
        self.assertEqual(list(f.qs), results)

    def test_with_date_min_before_pickup(self):
        now = timezone.now()
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=now - timedelta(hours=1),
            results=[pickup],
        )

    def test_with_date_min_during_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=halfway_datetime(pickup.date),
            results=[pickup],
        )

    def test_no_results_with_date_min_at_pickup_end(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=pickup.date_end,
            results=[],
        )

    def test_with_date_max_during_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_max=halfway_datetime(pickup.date),
            results=[pickup],
        )

    def test_with_date_max_after_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_max=pickup.date_end + timedelta(hours=2),
            results=[pickup],
        )

    def test_no_results_with_date_max_before_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_max=pickup.date_start - timedelta(hours=2),
            results=[],
        )

    def test_no_results_with_date_max_at_pickup_start(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_max=pickup.date_start,
            results=[],
        )

    def test_with_date_max_and_min_during_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=pickup.date_start + timedelta(seconds=5),
            date_max=pickup.date_end - timedelta(seconds=5),
            results=[pickup],
        )

    def test_with_date_max_and_min_overlapping_pickup_start(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=pickup.date_start - timedelta(seconds=5),
            date_max=pickup.date_start + timedelta(seconds=5),
            results=[pickup],
        )

    def test_with_date_max_and_min_overlapping_pickup_end(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=pickup.date_end - timedelta(seconds=5),
            date_max=pickup.date_end + timedelta(seconds=5),
            results=[pickup],
        )

    def test_with_date_max_and_min_containing_pickup(self):
        pickup = PickupDate.objects.create(store=self.store)
        self.expect_results(
            date_min=pickup.date_start - timedelta(seconds=5),
            date_max=pickup.date_end + timedelta(seconds=5),
            results=[pickup],
        )

    def test_fails_if_date_max_less_than_date_min(self):
        now = timezone.now()
        qs = PickupDate.objects.filter(store=self.store)
        with self.assertRaises(DataError):
            list(PickupDatesFilter(data={
                'date_min': now,
                'date_max': now - timedelta(hours=1),
            }, queryset=qs).qs)
