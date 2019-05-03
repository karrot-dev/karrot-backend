from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestPlacesAPIFilter(APITestCase):
    def setUp(self):
        self.url = '/api/places/'

        # two groups one place
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.group2 = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.place2 = PlaceFactory(group=self.group2)

    def test_filter_by_group(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.url, {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.place.name)

        response = self.client.get(self.url, {'group': self.group2.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.place2.name)

    def test_search_name(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.url, {'search': self.place.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.place.name)

    def test_search_description(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.url, {'search': self.place.description})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.place.name)
