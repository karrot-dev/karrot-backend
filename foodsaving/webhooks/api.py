import binascii

from anymail.exceptions import AnymailAPIError
from base64 import b64decode, b32decode, b32encode
from email.utils import parseaddr
from raven.contrib.django.raven_compat.models import client as sentry_client

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework import views, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from talon import quotations

from foodsaving.conversations.models import Conversation, ConversationMessage
from foodsaving.webhooks import stats
from foodsaving.webhooks.emails import prepare_incoming_email_rejected_email
from foodsaving.webhooks.models import EmailEvent, IncomingEmail


def parse_local_part(part):
    if part.startswith('b32+'):
        signed_part = b32decode(part[4:], casefold=True)
    else:
        # TODO: stay compatible with already sent emails, can be removed in some months
        signed_part = b64decode(part)
    signed_part_decoded = signed_part.decode('utf8')
    parts = signing.loads(signed_part_decoded)
    if len(parts) == 2:
        parts.append(None)  # in place of thread id
    return parts


def make_local_part(conversation, user, thread=None):
    data = [conversation.id, user.id]
    if thread is not None:
        data.append(thread.id)
    signed_part = signing.dumps(data)
    signed_part = signed_part.encode('utf8')
    b32 = b32encode(signed_part)
    b32_string = 'b32+' + b32.decode('utf8')
    return b32_string


def notify_about_rejected_email(user, content):
    try:
        prepare_incoming_email_rejected_email(user, content).send()
    except AnymailAPIError:
        sentry_client.captureException()
    stats.incoming_email_rejected()


class IncomingEmailView(views.APIView):
    permission_classes = (AllowAny, )

    def post(self, request):
        """
        Receive conversation replies via e-mail
        Request payload spec: https://developers.sparkpost.com/api/relay-webhooks/#header-relay-webhook-payload
        """

        auth_key = request.META.get('HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN')
        if auth_key is None or auth_key != settings.SPARKPOST_RELAY_SECRET:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={'message': 'Invalid HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN header'}
            )

        for messages in [e['msys'].values() for e in request.data]:
            for incoming_message in messages:
                # 1. get email content and reply-to
                reply_to = parseaddr(incoming_message['rcpt_to'])[1]
                content = incoming_message['content']

                # 2. check local part of reply-to and extract conversation and user (fail if they don't exist)
                local_part = reply_to.split('@')[0]
                try:
                    conversation_id, user_id, thread_id = parse_local_part(local_part)
                except (UnicodeDecodeError, binascii.Error):
                    sentry_client.captureException()
                    continue
                user = get_user_model().objects.get(id=user_id)

                thread = None
                if thread_id is not None:
                    thread = ConversationMessage.objects.get(id=thread_id)
                    conversation = thread.conversation
                else:
                    conversation = Conversation.objects.get(id=conversation_id)

                if not conversation.participants.filter(id=user.id).exists():
                    raise Exception('User not in conversation')

                # 3. extract the email reply text and add it to the conversation
                text_content = content['text']
                reply_plain = quotations.extract_from_plain(text_content)

                if conversation.is_closed:
                    notify_about_rejected_email(user, reply_plain)
                    continue

                created_message = ConversationMessage.objects.create(
                    author=user,
                    conversation=conversation,
                    thread=thread,
                    content=reply_plain,
                    received_via='email',
                )

                IncomingEmail.objects.create(
                    user=user,
                    message=created_message,
                    payload=incoming_message,
                )

        return Response(status=status.HTTP_200_OK, data={})


class EmailEventView(views.APIView):
    permission_classes = (AllowAny, )

    def authenticate(self, request):
        if 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    _, password = b64decode(auth[1]).decode().split(':', 1)
                    return password == settings.SPARKPOST_WEBHOOK_SECRET

    def post(self, request):
        """
        Receive e-mail related events via webhook (e.g. bounces)
        """

        if not self.authenticate(request):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'message': 'Invalid authorization header'})

        for events in [e['msys'].values() for e in request.data]:
            for event in events:
                EmailEvent.objects.update_or_create(
                    id=event['event_id'],
                    defaults={
                        'address': event['rcpt_to'],
                        'event': event['type'],
                        'payload': event
                    },
                )

        return Response(status=status.HTTP_200_OK, data={})
