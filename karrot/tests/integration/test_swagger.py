from rest_framework import status
from rest_framework.test import APITestCase

from karrot.users.factories import UserFactory


class TestSwaggerAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()

    def test_swagger_openapi(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/docs/schema/')
        self.assertEqual(response.accepted_media_type, 'application/vnd.oai.openapi')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('/api/groups/', response.data['paths'])

    def test_swagger_html(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/docs/')
        self.assertEqual(response.accepted_media_type, 'text/html')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
