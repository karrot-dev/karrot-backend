from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory
from karrot.activities.models import Feedback, to_range
from karrot.activities.factories import ActivityFactory


class TestFeedbackAPIFilter(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/feedback/'

        # create a group with a user and two places
        self.participant = UserFactory()
        self.participant2 = UserFactory()
        self.group = GroupFactory(members=[self.participant, self.participant2])
        self.group2 = GroupFactory(members=[self.participant, self.participant2])
        self.place = PlaceFactory(group=self.group)
        self.place2 = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1)))
        self.activity2 = ActivityFactory(place=self.place2, date=to_range(timezone.now() - relativedelta(days=1)))

        # create a feedback data
        self.feedback_get = {'given_by': self.participant, 'about': self.activity, 'weight': 1, 'comment': 'asfjk'}
        self.feedback_get2 = {'given_by': self.participant2, 'about': self.activity2, 'weight': 2, 'comment': 'bsfjk'}

        # create 2 instances of feedback
        self.feedback = Feedback.objects.create(**self.feedback_get)
        self.feedback2 = Feedback.objects.create(**self.feedback_get2)

        # transforms the user into a participant
        self.activity.add_participant(self.participant)
        self.activity2.add_participant(self.participant)
        self.activity2.add_participant(self.participant2)

    def test_filter_by_about(self):
        """
        Filter the two feedbacks and return the one that is about 'activity'
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.url, {'about': self.activity.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['feedback'][0]['about'], self.activity.id, response.data)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_given_by(self):
        """
        Filter the two feedbacks and return the one that is given_by 'participant'
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.url, {'given_by': self.participant.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['feedback'][0]['given_by'], self.participant.id)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_place(self):
        """
        Filter the two feedbacks and return the one that is about the activity at 'place'
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.url, {'place': self.place.id})
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback.id)
        self.assertEqual(response.data['feedback'][0]['about'], self.activity.id)
        self.assertEqual(len(response.data['feedback']), 1)

    def test_filter_by_place_2(self):
        """
        Filter the two feedbacks and return the one that is about the activity at 'place2'
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.url, {'place': self.place2.id})
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback2.id)
        self.assertEqual(response.data['feedback'][0]['about'], self.activity2.id)
        self.assertEqual(len(response.data['feedback']), 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_group(self):
        """
        Filter the two feedbacks by the places' group
        """
        self.client.force_login(user=self.participant)
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
        self.client.force_login(user=self.participant)
        # self.feedback is older than self.feedback2
        # first, get all that are newer than self.feedback
        response = self.get_results(self.url, {'created_at_after': self.feedback.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 2)
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback2.id)
        # second, get all that are older than self.feedback
        response = self.get_results(self.url, {'created_at_before': self.feedback.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['feedback']), 1)
        self.assertEqual(response.data['feedback'][0]['id'], self.feedback.id)
