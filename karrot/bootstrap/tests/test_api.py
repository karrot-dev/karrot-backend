from unittest.mock import ANY, patch

from django.test import override_settings
from geoip2.errors import AddressNotFoundError
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.users.factories import UserFactory
from karrot.utils.geoip import ip_to_city
from karrot.utils.tests.fake import faker

OVERRIDE_SETTINGS = {
    'SENTRY_CLIENT_DSN': faker.name(),
    'SENTRY_ENVIRONMENT': faker.name(),
    'FCM_CLIENT_API_KEY': faker.name(),
    'FCM_CLIENT_MESSAGING_SENDER_ID': faker.name(),
    'FCM_CLIENT_PROJECT_ID': faker.name(),
    'FCM_CLIENT_APP_ID': faker.name(),
}


class TestConfigAPI(APITestCase):
    def test_default_config(self):
        response = self.client.get('/api/config/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {
                'fcm': {
                    'api_key': None,
                    'messaging_sender_id': None,
                    'project_id': None,
                    'app_id': None,
                },
                'sentry': {
                    'dsn': None,
                    'environment': 'production',
                },
            }, response.data
        )

    @override_settings(**OVERRIDE_SETTINGS)
    def test_config_with_overrides(self):
        response = self.client.get('/api/config/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {
                'fcm': {
                    'api_key': OVERRIDE_SETTINGS['FCM_CLIENT_API_KEY'],
                    'messaging_sender_id': OVERRIDE_SETTINGS['FCM_CLIENT_MESSAGING_SENDER_ID'],
                    'project_id': OVERRIDE_SETTINGS['FCM_CLIENT_PROJECT_ID'],
                    'app_id': OVERRIDE_SETTINGS['FCM_CLIENT_APP_ID'],
                },
                'sentry': {
                    'dsn': OVERRIDE_SETTINGS['SENTRY_CLIENT_DSN'],
                    'environment': OVERRIDE_SETTINGS['SENTRY_ENVIRONMENT'],
                },
            }, response.data
        )


class TestBootstrapAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member], application_questions='')
        self.url = '/api/bootstrap/'
        self.client_ip = '2003:d9:ef08:4a00:4b7a:7964:8a3c:a33e'
        ip_to_city.cache_clear()  # prevent getting cached mock values

    def tearDown(self):
        ip_to_city.cache_clear()

    def test_as_anon(self):
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['server'], ANY)
        self.assertEqual(response.data['config'], ANY)
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

    @patch('karrot.utils.geoip.geoip')
    def test_without_geoip(self, geoip):
        geoip.city.side_effect = AddressNotFoundError
        response = self.client.get(self.url, HTTP_X_FORWARDED_FOR=self.client_ip)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['geoip'])

    def test_when_logged_in(self):
        self.client.force_login(user=self.user)
        with self.assertNumQueries(2):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['id'], self.user.id)
