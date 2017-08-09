from itertools import zip_longest

from dateutil.parser import parse
from dateutil import rrule
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from django.utils.datetime_safe import datetime

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory, PickupDateSeriesFactory
from foodsaving.stores.models import PickupDate, Feedback
from foodsaving.users.factories import UserFactory


class TestFeedbackAPI(APITestCase):
    """
    This is an unit test for the Feedback API
    """
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.now = timezone.now()
        cls.member = UserFactory()
        cls.group = GroupFactory(members=[cls.member, ])
        cls.store = StoreFactory(group=cls.group)
        cls.pickup = PickupDateFactory(store=cls.store)
        cls.series = PickupDateSeriesFactory(max_collectors=3, store=cls.store)
        cls.series.update_pickup_dates(start=lambda: cls.now)

    def test_new(self):
        """
        User is trying to give a feedback for a pickup
        that he didn't do (= not part of the collectors)?
        """
        user_feedback = Feedback()

        self.client.force_login(user=self.member)
        url = '/api/feedback/'.format(self.pickup)
        response = self.client.post(url, {'feedback': user_feedback.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {'user_feedback': ["something went wrong."]})




