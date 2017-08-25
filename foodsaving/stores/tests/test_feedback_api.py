from rest_framework import status
from rest_framework.test import APITestCase
from dateutil.relativedelta import relativedelta

from django.utils import timezone
from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.users.factories import UserFactory

# from foodsaving.stores.models import Feedback


class FeedbackTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.url = '/api/feedback/'

        """
        pickup date for group with one member and one store

        setup:
        1. create user
        2. create group with the user as member
        3. create a store within that group
        4. create a pickup within that store
        """

        cls.member = UserFactory()
        cls.collector = UserFactory()
        # create group and let 'member' and 'collector' join
        cls.group = GroupFactory(members=[cls.member, cls.collector])
        cls.store = StoreFactory(group=cls.group)
        cls.pickup = PickupDateFactory(store=cls.store)

        # not a member of the group
        cls.user = UserFactory()

        # past pickup date
        cls.past_pickup = PickupDateFactory(store=cls.store, date=timezone.now() - relativedelta(days=1))
        # transforms the menber into a collector
        cls.past_pickup.collectors.add(cls.collector)

        # create feedback
        cls.feedback = {
            'given_by': cls.member.id,
            'about': cls.past_pickup.id,
            'weight': 2,
            'comment': 'asfjk'
        }

    def test_create_feedback_fails_as_non_user(self):
        """
        Non-User is not allowed to give feedback.

        Test:
        1. user gives feedback to pickup
        2. make sure that response is NOT valid
        """
        response = self.client.post(self.url, self.feedback, format='json')

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_feedback_fails_as_non_group_member(self):
        """
        User is not allowed to give feedback when not a member of the stores group.

        Test:
        1. log user in
        2. user gives feedback to pickup
        3. make sure that response is NOT valid
        """
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.feedback, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['You are not member of the store\'s group.']})

    def test_create_feedback_fails_as_non_collector(self):
        """
        Group Member is not allowed to give feedback when he is not assiged to the
        Pickup.

        Test:
        1. log user in as group member
        2. user gives feedback to pickup
        3. feedback NOT created
        """
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.feedback, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['You aren\'t assign to the pickup.']})

    def test_create_feedback_works_as_collector(self):
        """
        Member is allowed to give feedback when he is assiged to the Pickup.

        Test:
        1. log user in as group member
        2. user gives feedback to pickup
        3. feedback created
        """
        self.client.force_login(user=self.collector)
        response = self.client.post(self.url, self.feedback, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_list_feedback_fails_as_non_user(self):
        """
        Non-User is NOT allowed to see list of feedback
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_feedback_works_as_non_group_member(self):
        """
        Non-Member is allowed to see an empty list of feedback
        """
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)
        # Why is this list empty?

    def test_list_feedback_works_as_group_member(self):
        """
        Member is allowed to see an empty list of feedback
        """
        self.client.force_login(user=self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_list_feedback_works_as_collector(self):
        """
        Collector is allowed to see list of feedback
        """
        self.client.force_login(user=self.collector)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        print(response.data)
        self.assertEqual(len(response.data), 2)
