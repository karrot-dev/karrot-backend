from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.places.factories import PlaceFactory
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory
from foodsaving.pickups.models import Feedback, to_range
from foodsaving.pickups.factories import PickupDateFactory


class TestFeedbackAPIFilter(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/feedback/'

        # create a group with a user and two places
        self.collector = UserFactory()
        self.collector2 = UserFactory()
        self.group = GroupFactory(members=[self.collector, self.collector2])
        self.group2 = GroupFactory(members=[self.collector, self.collector2])
        self.place = PlaceFactory(group=self.group)
        self.place2 = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1)))
        self.pickup2 = PickupDateFactory(place=self.place2, date=to_range(timezone.now() - relativedelta(days=1)))

        # create a feedback data
        self.feedback_get = {'given_by': self.collector, 'about': self.pickup, 'weight': 1, 'comment': 'asfjk'}
        self.feedback_get2 = {'given_by': self.collector2, 'about': self.pickup2, 'weight': 2, 'comment': 'bsfjk'}

        # create 2 instances of feedback
        self.feedback = Feedback.objects.create(**self.feedback_get)
        self.feedback2 = Feedback.objects.create(**self.feedback_get2)

        # transforms the user into a collector
        self.pickup.add_collector(self.collector)
        self.pickup2.add_collector(self.collector)
        self.pickup2.add_collector(self.collector2)

    def test_filter_by_about(self):
        """
        Filter the two feedbacks and return the one that is about 'pickup'
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.url, {'about': self.pickup.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['feedback'][0]['about'], self.pickup.id, response.data)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_given_by(self):
        """
        Filter the two feedbacks and return the one that is given_by 'collector'
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.url, {'given_by': self.collector.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['feedback'][0]['given_by'], self.collector.id)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_place(self):
        """
        Filter the two feedbacks and return the one that is about the pickup at 'place'
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.url, {'place': self.place.id})
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback.id)
        self.assertEqual(response.data['feedback'][0]['about'], self.pickup.id)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_place_2(self):
        """
        Filter the two feedbacks and return the one that is about the pickup at 'place2'
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.url, {'place': self.place2.id})
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback2.id)
        self.assertEqual(response.data['feedback'][0]['about'], self.pickup2.id)
        self.assertEqual(len(response.data['feedback']), 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_group(self):
        """
        Filter the two feedbacks by the places' group
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.url, {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 2)
        response = self.get_results(self.url, {'group': self.group2.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 0)

    def test_filter_by_created_at(self):
        """
        Filter the two feedbacks by creation date
        """
        self.client.force_login(user=self.collector)
        # self.feedback is older than self.feedback2
        # first, get all that are newer than self.feedback
        response = self.get_results(self.url, {'created_at_min': self.feedback.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 2)
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback2.id)
        # second, get all that are older than self.feedback
        response = self.get_results(self.url, {'created_at_max': self.feedback.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 1)
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback.id)
