from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from foodsaving.history.models import History
from foodsaving.pickups.factories import PickupDateFactory, \
    PickupDateSeriesFactory
from foodsaving.pickups.models import Feedback, PickupDate, PickupDateCollector, PickupDateSeries
from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.stores.models import StoreStatus
from foodsaving.users.factories import UserFactory


class TestFeedbackModel(TestCase):
    def setUp(self):
        self.pickup = PickupDateFactory()
        self.user = UserFactory()

    def test_weight_is_negative_fails(self):
        with self.assertRaises(ValidationError):
            model = Feedback.objects.create(weight=-1, about=self.pickup, given_by=self.user, comment="soup")
            model.clean_fields()

    def test_weight_is_too_high_number_fails(self):
        with self.assertRaises(ValidationError):
            model = Feedback.objects.create(weight=10001, about=self.pickup, given_by=self.user, comment="soup")
            model.clean_fields()

    def test_create_fails_if_comment_too_long(self):
        with self.assertRaises(DataError):
            Feedback.objects.create(comment='a' * 100001, about=self.pickup, given_by=self.user, weight=1)

    def test_create_two_feedback_for_same_pickup_as_same_user_fails(self):
        Feedback.objects.create(given_by=self.user, about=self.pickup)
        with self.assertRaises(IntegrityError):
            Feedback.objects.create(given_by=self.user, about=self.pickup)

    def test_create_two_feedback_for_different_pickups_as_same_user_works(self):
        Feedback.objects.create(given_by=self.user, about=self.pickup)
        Feedback.objects.create(given_by=self.user, about=PickupDateFactory())


class TestPickupDateSeriesModel(TestCase):
    def setUp(self):
        self.store = StoreFactory()

    def test_create_all_pickup_dates_inactive_stores(self):
        self.store.status = StoreStatus.ARCHIVED.value
        self.store.save()

        start_date = self.store.group.timezone.localize(datetime.now().replace(2017, 3, 18, 15, 0, 0, 0))

        PickupDateSeriesFactory(store=self.store, start_date=start_date)

        PickupDate.objects.all().delete()
        PickupDateSeries.objects.update_pickups()
        self.assertEqual(PickupDate.objects.count(), 0)

    def test_daylight_saving_time_to_summer(self):
        start_date = self.store.group.timezone.localize(datetime.now().replace(2017, 3, 18, 15, 0, 0, 0))

        before_dst_switch = timezone.now().replace(2017, 3, 18, 4, 40, 13)
        with freeze_time(before_dst_switch, tick=True):
            series = PickupDateSeriesFactory(store=self.store, start_date=start_date)

        expected_dates = []
        for month, day in [(3, 18), (3, 25), (4, 1), (4, 8)]:
            expected_dates.append(self.store.group.timezone.localize(datetime(2017, month, day, 15, 0)))
        for actual_date, expected_date in zip(PickupDate.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date, expected_date)

    def test_daylight_saving_time_to_winter(self):
        start_date = self.store.group.timezone.localize(datetime.now().replace(2016, 10, 22, 15, 0, 0, 0))

        before_dst_switch = timezone.now().replace(2016, 10, 22, 4, 40, 13)
        with freeze_time(before_dst_switch, tick=True):
            series = PickupDateSeriesFactory(store=self.store, start_date=start_date)

        expected_dates = []
        for month, day in [(10, 22), (10, 29), (11, 5), (11, 12)]:
            expected_dates.append(self.store.group.timezone.localize(datetime(2016, month, day, 15, 0)))
        for actual_date, expected_date in zip(PickupDate.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date, expected_date)

    def test_delete(self):
        now = timezone.now()
        two_weeks_ago = now - relativedelta(weeks=2)
        with freeze_time(two_weeks_ago, tick=True):
            series = PickupDateSeriesFactory(store=self.store, start_date=two_weeks_ago)

        pickup_dates = series.pickup_dates.all()
        past_date_count = pickup_dates.filter(date__lt=now).count()
        self.assertGreater(pickup_dates.count(), 2)
        series.delete()
        upcoming_pickups = PickupDate.objects.filter(date__gte=now, is_disabled=False)
        self.assertEqual(upcoming_pickups.count(), 0, upcoming_pickups)
        self.assertEqual(PickupDate.objects.filter(date__lt=now).count(), past_date_count)


class TestProcessFinishedPickupDates(TestCase):
    def setUp(self):
        self.pickup = PickupDateFactory(date=timezone.now() - relativedelta(weeks=1))

    def test_process_finished_pickup_dates(self):
        PickupDate.objects.process_finished_pickup_dates()
        self.assertEqual(PickupDate.objects.count(), 1)
        self.assertEqual(History.objects.count(), 1)

    def test_do_not_process_disabled_pickups(self):
        self.pickup.is_disabled = True
        self.pickup.save()
        PickupDate.objects.process_finished_pickup_dates()

        self.assertFalse(self.pickup.feedback_possible)
        self.assertEqual(History.objects.count(), 0)

    def test_disables_past_pickups_of_inactive_stores(self):
        store = self.pickup.store
        store.status = StoreStatus.ARCHIVED.value
        store.save()
        PickupDate.objects.process_finished_pickup_dates()

        self.assertEqual(History.objects.count(), 0)
        self.assertEqual(PickupDate.objects.count(), 1)
        self.assertTrue(PickupDate.objects.first().is_disabled)

        # do not process pickup again if stores gets active
        store.status = StoreStatus.ACTIVE.value
        store.save()
        PickupDate.objects.process_finished_pickup_dates()

        self.assertEqual(History.objects.count(), 0)


class TestAddPickupsCommand(TestCase):
    def setUp(self):
        self.series = PickupDateSeriesFactory()

    def test_update_pickups(self):
        PickupDateSeries.objects.update_pickups()
        self.assertGreater(PickupDate.objects.count(), 0)


class TestPickUpCollectors(TestCase):
    def setUp(self):
        self.first_member = UserFactory()
        self.second_member = UserFactory()
        self.group = GroupFactory(members=[self.first_member, self.second_member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

    def test_pickup_collectors_reverse_created_at_order(self):
        first_pickup_join_time = timezone.now()
        with freeze_time(first_pickup_join_time):
            first_pickup_join = PickupDateCollector.objects.create(user=self.first_member, pickupdate=self.pickup)
        self.assertTrue(first_pickup_join.created_at == first_pickup_join_time)

        second_pickup_join_time = first_pickup_join_time + timedelta(hours=1)
        with freeze_time(second_pickup_join_time):
            second_pickup_join = PickupDateCollector.objects.create(user=self.second_member, pickupdate=self.pickup)
        self.assertTrue(second_pickup_join.created_at == second_pickup_join_time)

        self.assertTrue(PickupDateCollector.objects.first() == second_pickup_join)
