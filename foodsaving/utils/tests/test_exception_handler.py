from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from foodsaving.users.factories import UserFactory


class TestCustomExceptionHandlerAPI(APITestCase):
    def test_use_token(self):
        response = self.client.get(
            '/api/auth/status/',
            **{
                'HTTP_AUTHORIZATION': 'Token {}'.format('invalidtoken'),
                'HTTP_ACCEPT_LANGUAGE': 'de',
            }
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['detail'], 'Ungültiges Token')
        self.assertEqual(response.data['error_code'], 'authentication_failed')
