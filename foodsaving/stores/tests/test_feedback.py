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
        cls.member = UserFactory()
        cls.group = GroupFactory(members=[cls.member])
        cls.store = StoreFactory(group=cls.group)
        cls.pickup = PickupDateFactory(store=cls.store)

        cls.feedback = {
            'given_by': cls.member.id,
            'about': cls.pickup.id,
            'weight': 2,
            'comment': 'asfjk'
        }

    def test_details(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_the_user_is_not_member_of_group(self):
        response = self.client.post(self.url, self.feedback)

        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, response.data)
