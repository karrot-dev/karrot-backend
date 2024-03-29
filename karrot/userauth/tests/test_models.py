from django.db.utils import IntegrityError
from django.test import TestCase

from karrot.userauth.models import VerificationCode
from karrot.users.factories import UserFactory


class TestVerificationCodeModel(TestCase):
    def setUp(self):
        self.user = UserFactory()

    def test_verification_code(self):
        loaded_code = VerificationCode.objects.get(user=self.user)
        self.assertFalse(loaded_code.has_expired())

    def test_unique_together(self):
        type_ = VerificationCode.PASSWORD_RESET
        VerificationCode.objects.create(user=self.user, type=type_)
        with self.assertRaises(IntegrityError):
            VerificationCode.objects.create(user=self.user, type=type_)
