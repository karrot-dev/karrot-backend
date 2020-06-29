from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from karrot.activities.models import Activity, to_range
from karrot.activities.utils import match_activities_with_dates


class TestMatchActivities(TestCase):
    def assertIteratorEqual(self, first, second, msg=None):
        self.assertEqual(list(first), list(second), msg)

    def test_matches_identical_activities(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        activities = [Activity(date=to_range(d, minutes=30)) for d in every_day]

        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_day),
            zip(activities, every_day),
        )

    def test_matches_partially(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        activities = [Activity(date=to_range(d, minutes=30)) for d in every_day]

        self.assertIteratorEqual(
            match_activities_with_dates(activities[::2], every_day),
            zip((activities[0], None, activities[2], None), every_day),
        )
        self.assertIteratorEqual(
            match_activities_with_dates(activities[1::2], every_day),
            zip((None, activities[1], None, activities[3]), every_day),
        )
        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_day[::2]),
            zip(activities, (every_day[0], None, every_day[2], None)),
        )
        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_day[1::2]),
            zip(activities, (None, every_day[1], None, every_day[3])),
        )

    def test_matches_shifted_activities_within_few_seconds(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 5)]
        activities = [Activity(date=to_range(d + relativedelta(seconds=20), minutes=30)) for d in every_day]

        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_day),
            zip(activities, every_day),
        )

    def test_not_matches_shifted_activities_with_more_difference(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 3)]
        activities = [Activity(date=to_range(d + relativedelta(minutes=10), minutes=30)) for d in every_day]

        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_day),
            [
                (None, every_day[0]),
                (activities[0], None),
                (None, every_day[1]),
                (activities[1], None),
            ],
        )

    def test_matches_first_when_distance_is_equal(self):
        now = timezone.now()

        # shift activities
        every_minute = [now + relativedelta(minutes=n) for n in range(1, 5)]
        activities = [Activity(date=to_range(d + relativedelta(seconds=30), minutes=30)) for d in every_minute]

        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_minute),
            zip(activities, every_minute),
        )

        # shift dates
        activities = [Activity(date=to_range(d, minutes=30)) for d in every_minute]
        every_minute = [n + relativedelta(seconds=30) for n in every_minute]

        self.assertIteratorEqual(
            match_activities_with_dates(activities, every_minute),
            zip(activities, every_minute),
        )

    def test_matches_empty(self):
        now = timezone.now()
        every_day = [now + relativedelta(days=n) for n in range(1, 3)]
        activities = [Activity(date=to_range(d, minutes=30)) for d in every_day]

        self.assertIteratorEqual(
            match_activities_with_dates([], every_day),
            zip((None, None), every_day),
        )
        self.assertIteratorEqual(
            match_activities_with_dates(activities, []),
            zip(activities, (None, None)),
        )
        self.assertIteratorEqual(
            match_activities_with_dates([], []),
            [],
        )
