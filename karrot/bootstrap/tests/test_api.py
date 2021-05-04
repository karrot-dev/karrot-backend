from unittest.mock import ANY, patch

from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class TestBootstrapAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member], application_questions='')
        self.url = '/api/bootstrap/'
        self.client_ip = '2003:d9:ef08:4a00:4b7a:7964:8a3c:a33e'

    def test_as_anon(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user'], None)
        self.assertEqual(response.data['geoip'], None)
        self.assertEqual(response.data['groups'], ANY)

    @patch('karrot.utils.geoip.geoip')
    def test_with_geoip(self, geoip):
        lat_lng = [float(val) for val in faker.latlng()]
        city = {'latitude': lat_lng[0], 'longitude': lat_lng[1], 'country_code': 'AA', 'time_zone': 'Europe/Berlin'}
        geoip.city.return_value = city
        response = self.client.get(self.url, HTTP_X_FORWARDED_FOR=self.client_ip)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            dict(response.data['geoip']), {
                'lat': city['latitude'],
                'lng': city['longitude'],
                'country_code': city['country_code'],
                'timezone': city['time_zone'],
            }
        )

    def test_when_logged_in(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['id'], self.user.id)
