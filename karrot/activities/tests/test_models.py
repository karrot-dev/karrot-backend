from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from karrot.history.models import History
from karrot.activities.factories import ActivityFactory, \
    ActivitySeriesFactory
from karrot.activities.models import Feedback, Activity, ActivitySeries, to_range
from karrot.places.factories import PlaceFactory
from karrot.places.models import PlaceStatusOld
from karrot.users.factories import UserFactory


class TestFeedbackModel(TestCase):
    def setUp(self):
        self.activity = ActivityFactory()
        self.user = UserFactory()

    def test_weight_is_negative_fails(self):
        with self.assertRaises(ValidationError):
            model = Feedback.objects.create(weight=-1, about=self.activity, given_by=self.user, comment="soup")
            model.clean_fields()

    def test_weight_is_too_high_number_fails(self):
        with self.assertRaises(ValidationError):
            model = Feedback.objects.create(weight=10001, about=self.activity, given_by=self.user, comment="soup")
            model.clean_fields()

    def test_create_fails_if_comment_too_long(self):
        with self.assertRaises(DataError):
            Feedback.objects.create(comment='a' * 100001, about=self.activity, given_by=self.user, weight=1)

    def test_create_two_feedback_for_same_activity_as_same_user_fails(self):
        Feedback.objects.create(given_by=self.user, about=self.activity)
        with self.assertRaises(IntegrityError):
            Feedback.objects.create(given_by=self.user, about=self.activity)

    def test_create_two_feedback_for_different_activities_as_same_user_works(self):
        Feedback.objects.create(given_by=self.user, about=self.activity)
        Feedback.objects.create(given_by=self.user, about=ActivityFactory())


class TestActivitySeriesModel(TestCase):
    def setUp(self):
        self.place = PlaceFactory()

    def test_create_all_activities_inactive_places(self):
        self.place.status = PlaceStatusOld.ARCHIVED.value
        self.place.save()

        start_date = self.place.group.timezone.localize(datetime.now().replace(2017, 3, 18, 15, 0, 0, 0))

        ActivitySeriesFactory(place=self.place, start_date=start_date)

        Activity.objects.all().delete()
        ActivitySeries.objects.update_activities()
        self.assertEqual(Activity.objects.count(), 0)

    def test_daylight_saving_time_to_summer(self):
        start_date = self.place.group.timezone.localize(datetime.now().replace(2017, 3, 18, 15, 0, 0, 0))

        before_dst_switch = timezone.now().replace(2017, 3, 18, 4, 40, 13)
        with freeze_time(before_dst_switch, tick=True):
            series = ActivitySeriesFactory(place=self.place, start_date=start_date)

        expected_dates = []
        for month, day in [(3, 18), (3, 25), (4, 1), (4, 8)]:
            expected_dates.append(self.place.group.timezone.localize(datetime(2017, month, day, 15, 0)))
        for actual_date, expected_date in zip(Activity.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date.start, expected_date)

    def test_daylight_saving_time_to_winter(self):
        start_date = self.place.group.timezone.localize(datetime.now().replace(2016, 10, 22, 15, 0, 0, 0))

        before_dst_switch = timezone.now().replace(2016, 10, 22, 4, 40, 13)
        with freeze_time(before_dst_switch, tick=True):
            series = ActivitySeriesFactory(place=self.place, start_date=start_date)

        expected_dates = []
        for month, day in [(10, 22), (10, 29), (11, 5), (11, 12)]:
            expected_dates.append(self.place.group.timezone.localize(datetime(2016, month, day, 15, 0)))
        for actual_date, expected_date in zip(Activity.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date.start, expected_date)

    def test_delete(self):
        now = timezone.now()
        two_weeks_ago = now - relativedelta(weeks=2)
        with freeze_time(two_weeks_ago, tick=True):
            series = ActivitySeriesFactory(place=self.place, start_date=two_weeks_ago)

        activities = series.activities.all()
        past_date_count = activities.filter(date__startswith__lt=now).count()
        self.assertGreater(activities.count(), 2)
        series.delete()
        upcoming_activities = Activity.objects.filter(date__startswith__gte=now, is_disabled=False)
        self.assertEqual(upcoming_activities.count(), 0, upcoming_activities)
        self.assertEqual(Activity.objects.filter(date__startswith__lt=now).count(), past_date_count)


class TestProcessFinishedActivities(TestCase):
    def setUp(self):
        self.activity = ActivityFactory(date=to_range(timezone.now() - relativedelta(weeks=1), minutes=30))

    def test_process_finished_activities(self):
        Activity.objects.process_finished_activities()
        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(History.objects.count(), 1)

    def test_handle_zero_max_participants_with_participants_joined(self):
        user = UserFactory()
        self.activity.group.add_member(user)
        self.activity.add_participant(user)
        History.objects.all().delete()

        self.activity.max_participants = 0
        self.activity.save()
        Activity.objects.process_finished_activities()

        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(History.objects.count(), 1)

    def test_do_not_process_disabled_activities(self):
        self.activity.is_disabled = True
        self.activity.save()
        Activity.objects.process_finished_activities()

        self.assertFalse(self.activity.is_done)
        self.assertEqual(History.objects.count(), 0)

    def test_disables_past_activities_of_inactive_places(self):
        place = self.activity.place
        place.status = PlaceStatusOld.ARCHIVED.value
        place.save()
        Activity.objects.process_finished_activities()

        self.assertEqual(History.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 1)
        self.assertTrue(Activity.objects.first().is_disabled)

        # do not process activity again if places gets active
        place.status = PlaceStatusOld.ACTIVE.value
        place.save()
        Activity.objects.process_finished_activities()

        self.assertEqual(History.objects.count(), 0)


class TestAddActivitiesCommand(TestCase):
    def setUp(self):
        self.series = ActivitySeriesFactory()

    def test_update_activities(self):
        ActivitySeries.objects.update_activities()
        self.assertGreater(Activity.objects.count(), 0)
