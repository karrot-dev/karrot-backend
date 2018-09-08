from rest_framework.test import APITestCase

from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory

bell_url = '/api/bells/'


class TestBellsAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_list_bells(self):
        self.client.force_login(self.member)
        # TODO create bell
        response = self.get_results(bell_url)
        self.assertEqual(len(response.data), 0)
