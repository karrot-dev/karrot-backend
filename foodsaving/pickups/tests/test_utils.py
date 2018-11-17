from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from foodsaving.pickups.models import PickupDate
from foodsaving.pickups.utils import match_pickups_with_dates


class TestMatchPickups(TestCase):
    def assertIteratorEqual(self, first, second, msg=None):
        self.assertEqual(list(first), list(second), msg)

    def test_matches_identical_pickups(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        pickups = [PickupDate(date=d) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day),
            zip(pickups, every_day),
        )

    def test_matches_partially(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        pickups = [PickupDate(date=d) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups[::2], every_day),
            zip((pickups[0], None, pickups[2], None), every_day),
        )
        self.assertIteratorEqual(
            match_pickups_with_dates(pickups[1::2], every_day),
            zip((None, pickups[1], None, pickups[3]), every_day),
        )
        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day[::2]),
            zip(pickups, (every_day[0], None, every_day[2], None)),
        )
        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day[1::2]),
            zip(pickups, (None, every_day[1], None, every_day[3])),
        )

    def test_matches_shifted_pickups(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        pickups = [PickupDate(date=d + relativedelta(hours=1)) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day),
            zip(pickups, every_day),
        )

        pickups = [PickupDate(date=d + relativedelta(hours=13)) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day),
            zip((None, *pickups), (*every_day, None)),
        )

    def test_matches_first_when_distance_is_equal(self):
        now = timezone.now()

        # shift pickups
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        pickups = [PickupDate(date=d + relativedelta(hours=12)) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day),
            zip(pickups, every_day),
        )

        # shift dates
        pickups = [PickupDate(date=d) for d in every_day]
        every_day = [now + relativedelta(hours=12) for n in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, every_day),
            zip(pickups, every_day),
        )

    def test_matches_empty(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 3)]
        pickups = [PickupDate(date=d) for d in every_day]

        self.assertIteratorEqual(
            match_pickups_with_dates([], every_day),
            zip((None, None), every_day),
        )
        self.assertIteratorEqual(
            match_pickups_with_dates(pickups, []),
            zip(pickups, (None, None)),
        )
        self.assertIteratorEqual(
            match_pickups_with_dates([], []),
            [],
        )
