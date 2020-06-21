import os

from anymail.inbound import AnymailInboundMessage
from anymail.signals import AnymailInboundEvent, EventType, AnymailTrackingEvent
from django.core import mail
from rest_framework.test import APITestCase

from karrot.conversations.factories import ConversationFactory
from karrot.conversations.models import ConversationMessage
from karrot.users.factories import UserFactory
from karrot.webhooks.models import EmailEvent, IncomingEmail
from karrot.webhooks.receivers import inbound_received, tracking_received
from karrot.webhooks.utils import make_local_part


class TestEmailReplyReceiver(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.conversation = ConversationFactory()
        self.conversation.join(self.user)

    def make_message(self, reply_token=None, text="message body", html=None):
        reply_token = reply_token or make_local_part(self.conversation, self.user)
        return AnymailInboundMessage.construct(
            to="{}@example.com".format(reply_token), text=text, html=html,
        )

    def send_message(self, inbound_message):
        inbound_received(
            sender=None,
            event=AnymailInboundEvent(
                event_type=EventType.INBOUND, message=inbound_message,
            ),
            esp_name="",
        )

    def test_receive_incoming_email(self):
        inbound_message = self.make_message()
        self.send_message(inbound_message)

        self.assertEqual(self.conversation.messages.count(), 1)
        message = ConversationMessage.objects.first()
        self.assertEqual(message.received_via, "email")
        self.assertEqual("message body", message.content)

        incoming_email = IncomingEmail.objects.first()
        self.assertEqual(incoming_email.user, self.user)
        self.assertEqual(incoming_email.payload["text"], inbound_message.text)
        self.assertEqual(incoming_email.message, message)

    def test_receive_incoming_email_with_only_html(self):
        with open(
            os.path.join(os.path.dirname(__file__), "./ms_outlook_2010.html")
        ) as f:
            html_message = f.read()

        inbound_message = self.make_message(text=None, html=html_message)

        self.send_message(inbound_message)

        self.assertEqual(self.conversation.messages.count(), 1)
        message = ConversationMessage.objects.first()
        self.assertEqual(message.received_via, "email")
        self.assertIn("Hi. I am fine.", message.content)

    def test_receive_incoming_email_with_casefolding(self):
        inbound_message = self.make_message()
        inbound_message.replace_header("to", inbound_message.to[0].addr_spec.lower())
        self.send_message(inbound_message)

        self.assertEqual(self.conversation.messages.count(), 1)
        message = ConversationMessage.objects.first()
        self.assertEqual(message.received_via, "email")

    def test_decode_error_is_silent(self):
        inbound_message = self.make_message()
        # make invalid reply-to field
        inbound_message.replace_header("to", inbound_message.to[0].addr_spec[10:])
        self.send_message(inbound_message)

        self.assertEqual(ConversationMessage.objects.count(), 0)

    def test_reject_incoming_email_if_conversation_is_closed(self):
        mail.outbox = []
        self.conversation.is_closed = True
        self.conversation.save()

        inbound_message = self.make_message()
        self.send_message(inbound_message)

        self.assertEqual(self.conversation.messages.count(), 0)
        self.assertEqual(IncomingEmail.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("not accepted", mail.outbox[0].subject)
        self.assertIn("message body", mail.outbox[0].body)


class TestEmailTrackingStatus(APITestCase):
    def test_receive_tracking_status(self):
        tracking_received(
            sender=None,
            event=AnymailTrackingEvent(
                event_id=4,
                event_type=EventType.BOUNCED,
                recipient="spam@example.com",
                esp_event={},
            ),
            esp_name="",
        )

        event = EmailEvent.objects.first()
        self.assertEqual(event.address, "spam@example.com")
        self.assertEqual(event.event, "bounced")
