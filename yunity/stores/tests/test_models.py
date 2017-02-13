from dateutil import rrule
from dateutil.relativedelta import relativedelta
from django.db import DataError
from django.test import TestCase
from django.utils import timezone
from datetime import datetime

from yunity.groups.factories import Group
from yunity.stores.factories import Store as StoreFactory
from yunity.stores.models import Store, PickupDateSeries, PickupDate


class TestStoreModel(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Group = Group()

    def test_create_fails_if_name_too_long(self):
        with self.assertRaises(DataError):
            Store.objects.create(name='a' * 81, group=self.Group)


class TestPickupDateSeriesModel(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = StoreFactory()
        cls.recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
        )

    def test_daylight_saving_time_to_summer(self):
        start_date = self.store.group.timezone.localize(datetime.now().replace(2017, 3, 18, 15, 0, 0, 0))

        series = PickupDateSeries(
            store=self.store,
            rule=str(self.recurrence),
            start_date=start_date
        )
        series.save()
        series.update_pickup_dates(start=lambda: timezone.now().replace(2017, 3, 18, 4, 40, 13))
        expected_dates = []
        for month, day in [
            (3, 18), (3, 25), (4, 1), (4, 8)
        ]:
            expected_dates.append(
                self.store.group.timezone.localize(datetime(2017, month, day, 15, 0))
            )
        for actual_date, expected_date in zip(PickupDate.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date, expected_date)

    def test_daylight_saving_time_to_winter(self):
        start_date = self.store.group.timezone.localize(datetime.now().replace(2016, 10, 22, 15, 0, 0, 0))

        series = PickupDateSeries(
            store=self.store,
            rule=str(self.recurrence),
            start_date=start_date
        )
        series.save()
        series.update_pickup_dates(start=lambda: timezone.now().replace(2016, 10, 22, 4, 40, 13))
        expected_dates = []
        for month, day in [
            (10, 22), (10, 29), (11, 5), (11, 12)
        ]:
            expected_dates.append(
                self.store.group.timezone.localize(datetime(2016, month, day, 15, 0))
            )
        for actual_date, expected_date in zip(PickupDate.objects.filter(series=series), expected_dates):
            self.assertEqual(actual_date.date, expected_date)

    def test_delete(self):
        now = timezone.now()
        two_weeks_ago = now - relativedelta(weeks=2)
        series = PickupDateSeries(
            store=self.store,
            rule=str(self.recurrence),
            start_date=two_weeks_ago
        )
        series.save()
        series.update_pickup_dates(start=lambda: two_weeks_ago)
        pickup_dates = series.pickup_dates.all()
        past_date_count = pickup_dates.filter(date__lt=now).count()
        self.assertGreater(pickup_dates.count(), 2)
        series.delete()
        self.assertEqual(PickupDate.objects.filter(date__gte=now).count(), 0)
        self.assertEqual(PickupDate.objects.filter(date__lt=now).count(), past_date_count)
