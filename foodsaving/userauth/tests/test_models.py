from django.test import TestCase

from foodsaving.users.factories import UserFactory
from foodsaving.userauth.models import VerificationCodeManager


class TestVerificationCodeManager(TestCase):
    def test_email_verification_code(self):
        user = UserFactory(mail_verified=False)
        user.save()
        manager = VerificationCodeManager(VerificationCodeManager.EMAIL_VERIFICATION)
        code = manager.get_code(user)
        self.assertEqual(manager.validate_code(code).email, user.email)
        user.mail_verified = True
        user.save()
        self.assertIsNone(manager.validate_code(code))

    # Comment in as soon as User has got a password_verified attribute
    #
    # def test_password_reset_verification_code(self):
    #     user = UserFactory(password_valid=False)
    #     user.save()
    #     manager = VerificationCodeManager(VerificationCodeManager.PASSWORD_RESET)
    #     code = manager.get_code(user)
    #     self.assertEqual(manager.validate_code(code).email, user.email)
    #     user.password_valid=True
    #     user.save()
    #     self.assertIsNone(manager.validate_code(code))

    # Comment in as soon as User has got a deletion_verified attribute
    #
    # def test_account_delete_verification_code(self):
    #     user = UserFactory()
    #     user.save()
    #     manager = VerificationCodeManager(VerificationCodeManager.ACCOUNT_DELETE)
    #     code = manager.get_code(user)
    #     self.assertEqual(manager.validate_code(code).email, user.email)
    #     user.delete()
    #     self.assertIsNone(manager.validate_code(code))

    def test_verification_code_expired(self):
        user = UserFactory(mail_verified=False)
        user.save()
        manager = VerificationCodeManager(VerificationCodeManager.EMAIL_VERIFICATION,
                                          debug_mode=VerificationCodeManager.DEBUG_VALIDITY_TIME_LIMIT)
        code = manager.get_code(user)
        self.assertIsNone(manager.validate_code(code))
