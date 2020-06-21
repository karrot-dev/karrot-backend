import binascii

from anymail.signals import tracking, inbound
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from raven.contrib.django.raven_compat.models import client as sentry_client

from karrot.conversations.models import ConversationMessage, Conversation
from karrot.utils.email_utils import generate_plaintext_from_html
from karrot.webhooks import stats
from karrot.webhooks.models import EmailEvent, IncomingEmail
from karrot.webhooks.utils import (
    parse_local_part,
    notify_about_rejected_email,
    trim_with_talon,
    trim_with_discourse,
)


@receiver(tracking)
def tracking_received(sender, event, esp_name, **kwargs):
    EmailEvent.objects.update_or_create(
        id=event.event_id,
        defaults={
            "address": event.recipient,
            "event": event.event_type,
            "payload": event.esp_event,
            "version": 2,
        },
    )


@receiver(inbound)
def inbound_received(sender, event, esp_name, **kwargs):
    incoming_message = event.message

    # check local part of reply-to and extract conversation and user (fail if they don't exist)
    local_part = incoming_message.to[0].username
    try:
        conversation_id, user_id, thread_id = parse_local_part(local_part)
    except (UnicodeDecodeError, binascii.Error):
        sentry_client.captureException()
        return
    user = get_user_model().objects.get(id=user_id)

    thread = None
    if thread_id is not None:
        thread = ConversationMessage.objects.get(id=thread_id)
        conversation = thread.conversation
    else:
        conversation = Conversation.objects.get(id=conversation_id)

    # get email content as plain text
    if incoming_message.text is not None:
        text_content = incoming_message.text
    elif incoming_message.html is not None:
        # let's just make HTML into plain text
        html_content = incoming_message.html
        text_content = generate_plaintext_from_html(html_content)
    else:
        # Inform the user if we couldn't find any content
        notify_about_rejected_email(user, "Karrot could not find any reply text")
        return

    # extract email reply text
    # Try out both talon and discourse email_reply_trimmer
    # Trimmers are conservative and sometimes keep more lines, leading to bloated replies.
    # We choose the trimmed reply that has fewer lines.

    trimmed_talon, line_count_talon = trim_with_talon(text_content)
    trimmed_discourse, line_count_discourse = trim_with_discourse(text_content)

    reply_plain = (
        trimmed_discourse if line_count_discourse <= line_count_talon else trimmed_talon
    )

    stats.incoming_email_trimmed(
        {
            "line_count_original": len(text_content.splitlines()),
            "line_count_talon": line_count_talon,
            "line_count_discourse": line_count_discourse,
            "from_html": 1 if incoming_message.text is None else 0,
        }
    )

    # add reply to conversation
    if conversation.is_closed:
        notify_about_rejected_email(user, reply_plain)
        return

    if not conversation.participants.filter(id=user.id).exists():
        notify_about_rejected_email(user, reply_plain)
        return

    created_message = ConversationMessage.objects.create(
        author=user,
        conversation=conversation,
        thread=thread,
        content=reply_plain,
        received_via="email",
    )

    incoming_message_serialized = dict(incoming_message)
    incoming_message_serialized["text"] = incoming_message.text
    incoming_message_serialized["html"] = incoming_message.html
    IncomingEmail.objects.create(
        user=user,
        message=created_message,
        payload=incoming_message_serialized,
        version=2,
    )
