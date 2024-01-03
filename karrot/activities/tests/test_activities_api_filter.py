from datetime import timedelta

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase

from django.utils import timezone

from karrot.groups.factories import GroupFactory
from karrot.activities.factories import ActivityFactory, ActivitySeriesFactory, FeedbackFactory, ActivityTypeFactory
from karrot.activities.models import Activity as ActivityModel, to_range
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory
from karrot.places.factories import PlaceFactory


class TestActivitydatesAPIFilter(APITestCase, ExtractPaginationMixin):
    def setUp(self):

        self.url = '/api/activities/'

        # activity for group with one member and one place
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity_type = ActivityTypeFactory(group=self.group)
        self.activity = ActivityFactory(activity_type=self.activity_type, place=self.place)

        # and another place + group + activity
        self.group2 = GroupFactory(members=[self.member])
        self.place2 = PlaceFactory(group=self.group2)
        self.activity_type2 = ActivityTypeFactory(group=self.group2)
        self.activity2 = ActivityFactory(activity_type=self.activity_type2, place=self.place2)

        # an activity series
        self.series = ActivitySeriesFactory(activity_type=self.activity_type, place=self.place)

        # another activity series
        self.series2 = ActivitySeriesFactory(activity_type=self.activity_type, place=self.place)

    def test_filter_by_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['place'], self.place.id)
        self.assertEqual(len(response.data), self.place.activities.count())

    def test_filter_by_group(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        place_ids = [_.id for _ in self.group.places.all()]
        for _ in response.data:
            self.assertTrue(_['place'] in place_ids)
        self.assertEqual(len(response.data), sum([place.activities.count() for place in self.group.places.all()]))

    def test_filter_by_series(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['series'], self.series.id)
        self.assertEqual(len(response.data), self.series.activities.count())

    def test_filter_after_date(self):
        self.client.force_login(user=self.member)
        query_date = self.activity.date.start + timedelta(days=1)
        response = self.get_results(self.url, {'date_min': query_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertGreater(parse(_['date'][0]), query_date)
        selected_activities = ActivityModel.objects.filter(place__group__members=self.member) \
            .filter(date__startswith__gte=query_date)
        self.assertEqual(len(response.data), selected_activities.count())

    def test_filter_before_date(self):
        self.client.force_login(user=self.member)
        query_date = self.activity.date.start + timedelta(days=10)
        response = self.get_results(self.url, {'date_max': query_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertLess(parse(_['date'][0]), query_date)
        selected_activities = ActivityModel.objects.filter(place__group__members=self.member) \
            .filter(date__startswith__lte=query_date)
        self.assertEqual(len(response.data), selected_activities.count())


class TestCustomActivityFilters(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/activities/'
        self.one_week_ago = to_range(timezone.now() - relativedelta(weeks=1))
        self.too_long_ago = to_range(
            timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS + 1), minutes=30
        )

        self.member = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(members=[self.member, self.member2])
        self.place = PlaceFactory(group=self.group)
        self.activity_type = ActivityTypeFactory(group=self.group)

        # not member (anymore)
        self.group2 = GroupFactory(members=[])
        self.place2 = PlaceFactory(group=self.group2)
        self.activity_type2 = ActivityTypeFactory(group=self.group2)

        self.activity_feedback_possible = ActivityFactory(
            activity_type=self.activity_type, place=self.place, participants=[
                self.member,
            ], date=self.one_week_ago
        )

        # now the issues where no feedback can be given
        self.activity_upcoming = ActivityFactory(
            activity_type=self.activity_type, place=self.place, participants=[
                self.member,
            ]
        )
        self.activity_not_participant = ActivityFactory(
            activity_type=self.activity_type, place=self.place, date=self.one_week_ago
        )
        self.activity_too_long_ago = ActivityFactory(
            activity_type=self.activity_type, place=self.place, date=self.too_long_ago, participants=[self.member]
        )

        self.activity_feedback_already_given = ActivityFactory(
            activity_type=self.activity_type, place=self.place, participants=[
                self.member,
            ], date=self.one_week_ago
        )

        self.feedback = FeedbackFactory(about=self.activity_feedback_already_given, given_by=self.member)

        self.activity_feedback_dismissed = ActivityFactory(
            activity_type=self.activity_type, place=self.place, participants=[
                self.member,
            ], date=self.one_week_ago
        )
        self.activity_feedback_dismissed.activityparticipant_set.filter(user=self.member
                                                                        ).update(feedback_dismissed=True)

        self.activity_participant_left_group = ActivityFactory(
            activity_type=self.activity_type2, place=self.place2, participants=[
                self.member,
            ], date=self.one_week_ago
        )
        self.activity_done_by_another_user = ActivityFactory(
            activity_type=self.activity_type, place=self.place, participants=[
                self.member2,
            ], date=self.one_week_ago
        )

        ActivityModel.objects.process_activities()

    def test_filter_feedback_possible(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'feedback_possible': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.activity_feedback_possible.id)

    def test_filter_joined(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'joined': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual({activity['id']
                          for activity in response.data}, {
                              self.activity_feedback_possible.id, self.activity_upcoming.id,
                              self.activity_too_long_ago.id, self.activity_feedback_already_given.id,
                              self.activity_feedback_dismissed.id
                          })

    def test_filter_not_joined(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'joined': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual({activity['id']
                          for activity in response.data},
                         {self.activity_not_participant.id, self.activity_done_by_another_user.id})
