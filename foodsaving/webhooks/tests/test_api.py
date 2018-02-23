from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.users.factories import UserFactory
from foodsaving.webhooks.api import make_local_part
from foodsaving.webhooks.models import EmailEvent


class TestEmailReplyAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.conversation = ConversationFactory()
        self.conversation.join(self.user)

    @override_settings(SPARKPOST_INCOMING_KEY='test_key')
    def test_receive_incoming_email(self):
        reply_token = make_local_part(self.conversation, self.user)
        response = self.client.post(
            '/api/webhooks/incoming_email/',
            data=[{'msys': {'relay_message': {
                'rcpt_to': '{}@example.com'.format(reply_token),
                'content': {'text': 'message body'}
            }}}],
            headers={'HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN': 'test_key'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(self.conversation.messages.count(), 1)


class TestEmailEventAPI(APITestCase):
    def test_receive_incoming_email(self):
        response = self.client.post(
            '/api/webhooks/email_event/',
            data=[{'msys': {'message_event': {
                'type': 'bounce',
                'rcpt_to': 'spam@example.com'
            }}}],
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        event = EmailEvent.objects.first()
        self.assertEqual(event.address, 'spam@example.com')
        self.assertEqual(event.event, 'bounce')

