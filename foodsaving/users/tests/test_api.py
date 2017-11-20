from datetime import timedelta

from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.utils.tests.fake import faker


class TestUsersAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.url = '/api/users/'
        self.user_data = {
            'email': faker.email(),
            'password': faker.name(),
            'display_name': faker.name(),
            'address': faker.address(),
            'latitude': faker.latitude(),
            'longitude': faker.longitude()
        }
        self.group = GroupFactory(members=[self.user, self.user2])
        self.another_common_group = GroupFactory(members=[self.user, self.user2])
        self.user_in_another_group = UserFactory()
        self.another_group = GroupFactory(members=[self.user_in_another_group, ])
        mail.outbox = []

    def test_list_users_forbidden(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_users_allowed(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_user_forbidden(self):
        url = self.url + str(self.user.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_user_allowed(self):
        self.client.force_login(user=self.user2)
        url = self.url + str(self.user.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], self.user.description)

    def test_retrieve_user_in_another_group_fails(self):
        self.client.force_login(user=self.user2)
        url = self.url + str(self.user_in_another_group.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestPasswordReset(APITestCase):
    def setUp(self):
        self.verified_user = VerifiedUserFactory(email='reset_test@example.com')
        self.url = '/api/users/reset_password/'
        mail.outbox = []

    def test_reset_password_succeeds(self):
        response = self.client.post(self.url, {'email': self.verified_user.email})
        self.assertEqual(response.data, {})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'New password')
        self.assertEqual(mail.outbox[0].to, [self.verified_user.email])

    def test_reset_password_fails_if_wrong_mail(self):
        response = self.client.post(self.url, {'email': 'wrong@example.com'})
        self.assertIsNone(response.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_fails_if_no_email(self):
        response = self.client.post(self.url)
        self.assertEqual(response.data, {'error': 'mail address is not provided'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_with_similar_email_succeeds(self):
        response = self.client.post(self.url, {'email': 'RESET_test@example.com'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.verified_user.email])


class TestEMailVerification(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.verified_user = VerifiedUserFactory()
        self.url = '/api/users/verify_mail/'

    def test_verify_mail_succeeds(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, {'key': self.user.activation_key})
        self.assertEqual(response.data, {})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_verify_mail_fails_if_not_logged_in(self):
        response = self.client.post(self.url, {'key': self.user.activation_key})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_mail_fails_with_wrong_key(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, {'key': 'w' * 40})
        self.assertEqual(response.data, {'key': ['Key is invalid']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_mail_fails_if_key_too_old(self):
        self.client.force_login(user=self.user)
        backup = self.user.key_expires_at
        self.user.key_expires_at = timezone.now() - timedelta(days=1)
        self.user.save()
        response = self.client.post(self.url, {'key': self.user.activation_key})
        self.assertEqual(response.data, {'key': ['Key has expired']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.key_expires_at = backup
        self.user.save()

    def test_verify_mail_fails_if_already_verified(self):
        self.client.force_login(user=self.verified_user)
        response = self.client.post(self.url, {'key': self.user.activation_key})
        self.assertEqual(response.data['detail'], 'Mail is already verified.')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_mail_fails_without_key(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.data, {'key': ['This field is required.']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestResendEMailVerificationKey(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.verified_user = VerifiedUserFactory()
        self.url = '/api/users/resend_verification/'
        mail.outbox = []

    def test_resend_verification_succeeds(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Please verify your email')
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertNotIn('Thank you for signing up', mail.outbox[0].body)

    def test_resend_verification_fails_if_already_verified(self):
        self.client.force_login(user=self.verified_user)
        response = self.client.post(self.url)
        self.assertEqual(response.data, {'error': 'Already verified'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resend_verification_fails_if_not_logged_in(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
