from rest_framework import status
from rest_framework.test import APITestCase

from karrot.activities.factories import ActivityFactory, ActivityTypeFactory
from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestActivitiesAPIICSToken(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/api/activities/'

        # activity for group with one member and one place
        cls.member = UserFactory()
        cls.group = GroupFactory(members=[cls.member])
        cls.place = PlaceFactory(group=cls.group)
        cls.activity_type = ActivityTypeFactory(group=cls.group)
        cls.activity = ActivityFactory(activity_type=cls.activity_type, place=cls.place)

    def setUp(self):
        self.group.refresh_from_db()

    def test_export_ics_with_token(self):
        self.client.force_login(self.member)
        response = self.client.get('/api/activities/ics_token/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        token = response.data

        self.client.logout()
        response = self.client.get(f'/api/activities/ics/?token={token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_refresh_token(self):
        self.client.force_login(self.member)
        response = self.client.post('/api/activities/ics_token_refresh/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        old_token = response.data

        response = self.client.post('/api/activities/ics_token_refresh/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        new_token = response.data

        self.client.logout()
        response = self.client.get(f'/api/activities/ics/?token={old_token}')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)

        response = self.client.get(f'/api/activities/ics/?token={new_token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_export_ics_fails_with_invalid_token(self):
        response = self.client.get('/api/activities/ics/?token=invalid')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)

    def test_export_ics_fails_without_token(self):
        response = self.client.get('/api/activities/ics/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)
