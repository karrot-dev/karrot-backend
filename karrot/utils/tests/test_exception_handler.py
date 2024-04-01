from rest_framework import status
from rest_framework.test import APITestCase


class TestCustomExceptionHandlerAPI(APITestCase):
    def test_reports_error_code(self):
        response = self.client.get(
            "/api/auth/user/", headers={"authorization": "Token {}".format("invalidtoken"), "accept-language": "de"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Ungültiges Token")
        self.assertEqual(response.data["error_code"], "authentication_failed")
