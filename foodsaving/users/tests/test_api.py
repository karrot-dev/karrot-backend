from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.groups.factories import GroupFactory
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory
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
        self.another_group = GroupFactory(members=[
            self.user_in_another_group,
        ])
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

    def test_get_conversation(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/users/{}/conversation/'.format(self.user2.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.user.id, response.data['participants'])
        self.assertIn(self.user2.id, response.data['participants'])
        self.assertEqual(len(response.data['participants']), 2)

    def test_get_conversation_for_yourself_fails(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/users/{}/conversation/'.format(self.user.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestPublicUserProfilesAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.user = UserFactory()
        self.users = [UserFactory() for _ in range(10)] + [self.user]
        self.user_not_in_conversation = UserFactory()
        # filters user who share a conversation, so add all to one
        ConversationFactory(participants=self.users)

    def test_list_public_profiles(self):
        self.client.force_login(user=self.user)
        response = self.get_results('/api/users-info/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), len(self.users))
        user_response = next(r for r in response.data if r['id'] == self.user.id)
        self.assertEqual(user_response, {
            'display_name': self.user.display_name,
            'id': self.user.id,
        })
        self.assertFalse(any(r['id'] == self.user_not_in_conversation.id for r in response.data))

    def test_access_forbidden_if_not_logged_in(self):
        response = self.get_results('/api/users-info/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_conversation(self):
        more_users = [UserFactory() for _ in range(3)] + [self.user]
        another_conversation = ConversationFactory(participants=more_users)
        self.client.force_login(user=self.user)
        response = self.get_results('/api/users-info/?conversation={}'.format(another_conversation.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), len(more_users))
