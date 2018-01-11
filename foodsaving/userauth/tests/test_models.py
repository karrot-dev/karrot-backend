from django.test import TestCase

from foodsaving.users.factories import UserFactory
from foodsaving.userauth.models import VerificationCode

# TODO: Integration tests


class TestVerificationCodeModel(TestCase):
    def setUp(self):
        self.user = UserFactory(mail_verified=False)
        self.verification_code = VerificationCode(user=self.user, type=VerificationCode.EMAIL_VERIFICATION)
        self.user.save()
        self.verification_code.save()

    def test_verification_code(self):
        loaded_code = VerificationCode.objects.get(user=self.user)
        self.assertTrue(loaded_code.is_valid(self.verification_code.code, self.user, self.verification_code.type))

        self.verification_code.invalidate()
        loaded_code = VerificationCode.objects.get(user=self.user)
        self.assertFalse(loaded_code.is_valid(self.verification_code.code, self.user, self.verification_code.type))
