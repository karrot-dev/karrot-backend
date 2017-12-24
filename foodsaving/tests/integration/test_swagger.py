import unittest

from rest_framework import status
from rest_framework.test import APITestCase
from foodsaving.users.factories import UserFactory


class TestAPIDocumentation(APITestCase):
    """
    Just some basic smoke tests for now
    """
    def setUp(self):
        self.user = UserFactory()

    def test_swagger_json(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/schema.json')
        self.assertEqual(response.accepted_media_type, 'application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_html(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/docs/')
        self.assertEqual(response.accepted_media_type, 'text/html')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
