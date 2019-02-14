from datetime import timedelta

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase

from django.utils import timezone

from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory, PickupDateSeriesFactory, FeedbackFactory
from foodsaving.pickups.models import PickupDate as PickupDateModel, to_range
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory
from foodsaving.places.factories import PlaceFactory


class TestPickupdatesAPIFilter(APITestCase, ExtractPaginationMixin):
    def setUp(self):

        self.url = '/api/pickup-dates/'

        # pickup date for group with one member and one place
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place)

        # and another place + group + pick-update
        self.group2 = GroupFactory(members=[self.member])
        self.place2 = PlaceFactory(group=self.group2)
        self.pickup2 = PickupDateFactory(place=self.place2)

        # a pickup date series
        self.series = PickupDateSeriesFactory(place=self.place)

        # another pickup date series
        self.series2 = PickupDateSeriesFactory(place=self.place)

    def test_filter_by_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['place'], self.place.id)
        self.assertEqual(len(response.data), self.place.pickup_dates.count())

    def test_filter_by_group(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        place_ids = [_.id for _ in self.group.places.all()]
        for _ in response.data:
            self.assertTrue(_['place'] in place_ids)
        self.assertEqual(len(response.data), sum([place.pickup_dates.count() for place in self.group.places.all()]))

    def test_filter_by_series(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['series'], self.series.id)
        self.assertEqual(len(response.data), self.series.pickup_dates.count())

    def test_filter_after_date(self):
        self.client.force_login(user=self.member)
        query_date = self.pickup.date.start + timedelta(days=1)
        response = self.get_results(self.url, {'date_min': query_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertGreater(parse(_['date'][0]), query_date)
        selected_pickups = PickupDateModel.objects.filter(place__group__members=self.member) \
            .filter(date__startswith__gte=query_date)
        self.assertEqual(len(response.data), selected_pickups.count())

    def test_filter_before_date(self):
        self.client.force_login(user=self.member)
        query_date = self.pickup.date.start + timedelta(days=10)
        response = self.get_results(self.url, {'date_max': query_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertLess(parse(_['date'][0]), query_date)
        selected_pickups = PickupDateModel.objects.filter(place__group__members=self.member) \
            .filter(date__startswith__lte=query_date)
        self.assertEqual(len(response.data), selected_pickups.count())


class TestFeedbackPossibleFilter(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/pickup-dates/'
        self.oneWeekAgo = to_range(timezone.now() - relativedelta(weeks=1))
        self.tooLongAgo = to_range(
            timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS + 1), minutes=30
        )

        self.member = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(members=[self.member, self.member2])
        self.place = PlaceFactory(group=self.group)

        # not member (anymore)
        self.group2 = GroupFactory(members=[])
        self.place2 = PlaceFactory(group=self.group2)

        self.pickupFeedbackPossible = PickupDateFactory(
            place=self.place, collectors=[
                self.member,
            ], date=self.oneWeekAgo
        )

        # now the issues where no feedback can be given
        self.pickupUpcoming = PickupDateFactory(
            place=self.place, collectors=[
                self.member,
            ]
        )
        self.pickupNotCollector = PickupDateFactory(place=self.place, date=self.oneWeekAgo)
        self.pickupTooLongAgo = PickupDateFactory(place=self.place, date=self.tooLongAgo)

        self.pickupFeedbackAlreadyGiven = PickupDateFactory(
            place=self.place, collectors=[
                self.member,
            ], date=self.oneWeekAgo
        )
        self.feedback = FeedbackFactory(about=self.pickupFeedbackAlreadyGiven, given_by=self.member)

        self.pickupCollectorLeftGroup = PickupDateFactory(
            place=self.place2, collectors=[
                self.member,
            ], date=self.oneWeekAgo
        )
        self.pickupDoneByAnotherUser = PickupDateFactory(
            place=self.place, collectors=[
                self.member2,
            ], date=self.oneWeekAgo
        )

        PickupDateModel.objects.process_finished_pickup_dates()

    def test_filter_feedback_possible(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'feedback_possible': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.pickupFeedbackPossible.id)
