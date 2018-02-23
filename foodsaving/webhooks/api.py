from base64 import b64decode, b64encode
from email.utils import parseaddr

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework import views, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from talon import quotations

from foodsaving.conversations.models import Conversation, ConversationMessage


class IncomingEmailView(views.APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        """
        Receive conversation replies via e-mail
        """

        auth_key = request.META['headers'].get('HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN')
        if auth_key is None or auth_key != settings.SPARKPOST_INCOMING_KEY:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={'message': 'Invalid HTTP_X_MESSAGESYSTEMS_WEBHOOK_TOKEN header'}
            )

        # 1. get email content and reply-to
        relay_message = request.data[0]['msys']['relay_message']
        reply_to = parseaddr(relay_message['rcpt_to'])[1]
        content = relay_message['content']

        # 2. check local part of reply-to and extract conversation and user (fail if they don't exist)
        local_part = reply_to.split('@')[0]
        conversation_id, user_id = parse_local_part(local_part)
        conversation = Conversation.objects.get(id=conversation_id)
        user = get_user_model().objects.get(id=user_id)

        if not conversation.participants.filter(id=user.id).exists():
            raise Exception('User not in conversation')

        # 3. extract the email reply text and add it to the conversation
        text_content = content['text']
        reply_plain = quotations.extract_from_plain(text_content)

        ConversationMessage.objects.create(
            author=user,
            conversation=conversation,
            content=reply_plain,
        )

        return Response(status=status.HTTP_204_NO_CONTENT, data={})


def parse_local_part(part):
    signed_part = b64decode(part)
    signed_part_decoded = signed_part.decode('utf8')
    conversation_and_user = signing.loads(signed_part_decoded)
    return conversation_and_user


def make_local_part(conversation, user):
    signed_part = signing.dumps([conversation.id, user.id])
    signed_part = signed_part.encode('utf8')
    encoded = b64encode(signed_part)
    return encoded.decode('utf8')
