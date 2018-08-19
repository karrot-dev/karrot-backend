from anymail.exceptions import AnymailAPIError
from huey.contrib.djhuey import db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

import foodsaving.conversations.emails
from foodsaving.conversations.models import ConversationParticipant, ConversationThreadParticipant
from foodsaving.groups.models import GroupMembership
from foodsaving.users.models import User


@db_task()
def notify_participants(message):
    # skip this notification if this is not the most recent message
    all_messages = message.conversation.messages
    if message.is_thread_reply():
        latest_message = all_messages.only_replies().latest('created_at')
    else:
        latest_message = all_messages.exclude_replies().latest('created_at')
    if latest_message.id != message.id:
        return

    if message.is_thread_reply():
        participants_to_notify = ConversationThreadParticipant.objects.filter(
            thread=message.thread,
            muted=False,
        )
    else:
        participants_to_notify = ConversationParticipant.objects.filter(
            conversation=message.conversation,
            email_notifications=True,
        )

    participants_to_notify = participants_to_notify.exclude(
        user=message.author,
    ).exclude(
        user__in=User.objects.unverified_or_ignored(),
    ).exclude(
        seen_up_to__id__gte=message.id,
    ).exclude(
        notified_up_to__id__gte=message.id,
    )

    # TODO: consider if we want to always send thread notifications even to inactive users
    if message.conversation.type() == 'group':
        # if it's a group conversation, only send to users who are active in that group
        participants_to_notify = participants_to_notify.filter(
            user__groupmembership__in=GroupMembership.objects.active(),
            user__groupmembership__group=message.conversation.target,
        )

    for participant in participants_to_notify.distinct():
        messages = participant.unseen_and_unnotified_messages().all()
        try:
            foodsaving.conversations.emails.prepare_conversation_message_notification(
                user=participant.user,
                messages=messages,
            ).send()
        except AnymailAPIError:
            sentry_client.captureException()
        else:
            participant.notified_up_to = message
            participant.save()
