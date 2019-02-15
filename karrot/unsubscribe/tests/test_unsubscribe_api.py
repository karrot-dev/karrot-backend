from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupNotificationType
from karrot.places.factories import PlaceFactory
from karrot.unsubscribe.utils import generate_token
from karrot.users.factories import UserFactory


class TestUnsubscribeAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.url = '/api/unsubscribe/{}/'
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.place = PlaceFactory(group=self.group)
        self.other_group = GroupFactory(members=[self.user])

    def test_unsubscribe_from_conversation(self):
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        token = generate_token(self.user, self.group, conversation=self.group.conversation)
        self.assertFalse(participant.get().muted)
        self.client.post(self.url.format(token), {'choice': 'conversation'}, format='json')
        self.assertTrue(participant.get().muted)

    def test_unsubscribe_from_thread(self):
        thread = self.group.conversation.messages.create(author=self.user, content='foo')
        self.group.conversation.messages.create(author=self.user, content='foo reply', thread=thread)
        token = generate_token(self.user, self.group, thread=thread)
        participant = thread.participants.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        self.client.post(self.url.format(token), {'choice': 'thread'}, format='json')
        self.assertTrue(participant.get().muted)

    def test_unsubscribe_from_notification_type(self):
        token = generate_token(
            self.user,
            group=self.group,
            notification_type=GroupNotificationType.NEW_APPLICATION,
        )
        notification_types = self.group.groupmembership_set.filter(user=self.user).values_list(
            'notification_types',
            flat=True,
        )
        self.assertIn('new_application', notification_types.get())
        self.client.post(self.url.format(token), {'choice': 'notification_type'}, format='json')
        self.assertNotIn('new_application', notification_types.get())

    def test_unsubscribe_from_group(self):
        token = generate_token(self.user, self.group)
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        self.client.post(self.url.format(token), {'choice': 'group'}, format='json')
        self.assertTrue(participant.get().muted)

    def test_does_not_unsubscribe_from_other_group(self):
        token = generate_token(self.user, self.group)
        participant = self.other_group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        self.client.post(self.url.format(token), {'choice': 'group'}, format='json')
        self.assertFalse(participant.get().muted)

    def test_fails_with_invalid_token(self):
        response = self.client.post(self.url.format('invalidtoken'), {'choice': 'group'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_fails_without_a_conversation(self):
        token = generate_token(self.user, self.group)
        response = self.client.post(self.url.format(token), {'choice': 'conversation'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_fails_without_a_thread(self):
        token = generate_token(self.user, self.group, conversation=self.group.conversation)
        response = self.client.post(self.url.format(token), {'choice': 'thread'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_fails_without_a_group(self):
        token = generate_token(self.user, conversation=self.group.conversation)
        response = self.client.post(self.url.format(token), {'choice': 'group'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
