from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.users.factories import VerifiedUserFactory
from foodsaving.userauth.models import VerificationCode


class TestRequestPasswordReset(APITestCase):
    def setUp(self):
        self.verified_user = VerifiedUserFactory(email='reset_test@example.com')
        self.password = 'forgotten'
        self.url = '/api/auth/reset_password/request/'
        mail.outbox = []

    def test_request_reset_password_succeeds(self):
        response = self.client.post(self.url, {'email': self.verified_user.email})
        self.assertEqual(response.data, {})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Forgot your password?')
        self.assertEqual(mail.outbox[0].to, [self.verified_user.email])

    def test_request_reset_password_fails_if_wrong_mail(self):
        response = self.client.post(self.url, {'email': 'wrong@example.com'})
        self.assertEqual(response.data, {'email': ['Unknown e-mail address']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_reset_password_fails_if_no_email(self):
        response = self.client.post(self.url)
        self.assertEqual(response.data, {'email': ['This field is required.']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_reset_password_with_similar_email_succeeds(self):
        response = self.client.post(self.url, {'email': 'RESET_test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.verified_user.email])

    def test_request_reset_password_disables_login(self):
        self.client.post(self.url, {'email': 'RESET_test@example.com'})
        self.assertFalse(self.client.login(email=self.verified_user.email, password=self.password))


class TestPasswordReset(APITestCase):
    def setUp(self):
        self.verified_user = VerifiedUserFactory(email='reset_test@example.com')
        self.url_request_password_reset = '/api/auth/reset_password/request/'
        self.url_password_reset = '/api/auth/reset_password/'
        self.type = VerificationCode.PASSWORD_RESET
        self.old_password = 'forgotten'
        self.new_password = 'super-safe'
        self.verified_user.set_password(self.old_password)
        mail.outbox = []

    def test_request_reset_password_succeeds(self):
        self.client.post(self.url_request_password_reset, {'email': self.verified_user.email})
        code = VerificationCode.objects.get(user=self.verified_user, type=self.type).code
        response = self.client.post(self.url_password_reset, {'code': code, 'new_password': self.new_password})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, 'New password set!')
        self.assertEqual(mail.outbox[1].to, [self.verified_user.email])

        # Login with the old password does not work
        self.assertFalse(self.client.login(email=self.verified_user.email, password=self.old_password))
        # Login with the new password works
        self.assertTrue(self.client.login(email=self.verified_user.email, password=self.new_password))
