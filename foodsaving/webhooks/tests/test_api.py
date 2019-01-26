from base64 import b64encode
from django.core import mail

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import ConversationMessage
from foodsaving.users.factories import UserFactory
from foodsaving.webhooks.api import make_local_part
from foodsaving.webhooks.models import EmailEvent, IncomingEmail


class TestEmailReplyAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.conversation = ConversationFactory()
        self.conversation.join(self.user)

    def make_message(self):
        reply_token = make_local_part(self.conversation, self.user)
        relay_message = {
            'rcpt_to': '{}@example.com'.format(reply_token),
            'content': {
                'text': 'message body'
            },
        }
        return relay_message

    def send_message(self, relay_message):
        response = self.client.post(
            '/api/webhooks/incoming_email/',
            data=[{
                'msys': {
                    'relay_message': relay_message
                }
            }],
            HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN='test_key',
            format='json'
        )
        return response

    @override_settings(SPARKPOST_RELAY_SECRET='test_key')
    def test_receive_incoming_email(self):
        relay_message = self.make_message()
        response = self.send_message(relay_message)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.conversation.messages.count(), 1)
        message = ConversationMessage.objects.first()
        self.assertEqual(message.received_via, 'email')

        incoming_email = IncomingEmail.objects.first()
        self.assertEqual(incoming_email.user, self.user)
        self.assertEqual(incoming_email.payload, relay_message)
        self.assertEqual(incoming_email.message, message)

    @override_settings(SPARKPOST_RELAY_SECRET='test_key')
    def test_reject_incoming_email_if_conversation_is_closed(self):
        mail.outbox = []
        self.conversation.is_closed = True
        self.conversation.save()

        relay_message = self.make_message()
        response = self.send_message(relay_message)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.conversation.messages.count(), 0)
        self.assertEqual(IncomingEmail.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('not accepted', mail.outbox[0].subject)
        self.assertIn('message body', mail.outbox[0].body)


class TestEmailEventAPI(APITestCase):
    @override_settings(SPARKPOST_WEBHOOK_SECRET='test_key')
    def test_receive_incoming_email(self):
        basic_auth = 'basic {}'.format(b64encode('asdf:test_key'.encode()).decode())
        response = self.client.post(
            '/api/webhooks/email_event/',
            data=[{
                'msys': {
                    'message_event': {
                        'event_id': 4,
                        'type': 'bounce',
                        'rcpt_to': 'spam@example.com'
                    }
                }
            }],
            HTTP_AUTHORIZATION=basic_auth,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        event = EmailEvent.objects.first()
        self.assertEqual(event.address, 'spam@example.com')
        self.assertEqual(event.event, 'bounce')
