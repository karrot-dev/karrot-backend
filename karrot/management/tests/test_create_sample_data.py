from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from karrot.users.models import User


class TestCreateSampleData(APITestCase):
    def test_run_command(self):
        out = StringIO()
        call_command("create_sample_data", "--quick", stdout=out)
        self.assertGreater(User.objects.count(), 0)
