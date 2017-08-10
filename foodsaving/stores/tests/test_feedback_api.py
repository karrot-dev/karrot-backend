from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.users.factories import UserFactory

# from foodsaving.stores.models import Feedback


class FeedbackTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.url = '/api/feedback/'

        # pickup date for group with one member and one store
        cls.member = UserFactory()
        cls.group = GroupFactory(members=[cls.member])
        cls.store = StoreFactory(group=cls.group)
        cls.pickup = PickupDateFactory(store=cls.store)

        # not a member of the group
        cls.user = UserFactory()

        # create feedback
        cls.feedback = {
            'given_by': cls.member.id,
            'about': cls.pickup.id,
            'weight': 2,
            'comment': 'asfjk'
        }

    def test_create_feedback(self):
        response = self.client.post(self.url, self.feedback, format='json')

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_feedback_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.feedback, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'given_by': ['You are not member of the store\'s group.']})
