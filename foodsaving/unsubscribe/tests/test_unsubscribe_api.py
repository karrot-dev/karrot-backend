from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.unsubscribe.utils import generate_token
from foodsaving.users.factories import UserFactory


class TestUnsubscribeAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.url = '/api/unsubscribe/{}/'
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.store = StoreFactory(group=self.group)

    def test_unsubscribe_from_conversation(self):
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        token = generate_token(self.user, self.group, conversation=self.group.conversation)
        self.assertTrue(participant.get().email_notifications)
        self.client.post(self.url.format(token), {'choice': 'conversation'}, format='json')
        self.assertFalse(participant.get().email_notifications)

    def test_unsubscribe_from_thread(self):
        thread = self.group.conversation.messages.create(author=self.user, content='foo')
        self.group.conversation.messages.create(author=self.user, content='foo reply', thread=thread)
        token = generate_token(self.user, self.group, thread=thread)
        participant = thread.participants.filter(user=self.user)
        self.assertFalse(participant.get().muted)
        self.client.post(self.url.format(token), {'choice': 'thread'}, format='json')
        self.assertTrue(participant.get().muted)

    def test_unsubscribe_from_group(self):
        token = generate_token(self.user, self.group)
        participant = self.group.conversation.conversationparticipant_set.filter(user=self.user)
        self.assertTrue(participant.get().email_notifications)
        self.client.post(self.url.format(token), {'choice': 'group'}, format='json')
        self.assertFalse(participant.get().email_notifications)
