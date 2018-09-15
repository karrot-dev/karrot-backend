from rest_framework.test import APITestCase

from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory

notification_url = '/api/notifications/'


class TestNotificationsAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_list_notifications(self):
        self.client.force_login(self.member)
        # TODO create notification
        response = self.get_results(notification_url)
        self.assertEqual(len(response.data), 0)
