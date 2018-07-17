from anymail.exceptions import AnymailAPIError
from huey.contrib.djhuey import db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

import foodsaving.conversations.emails
from foodsaving.conversations.models import ConversationParticipant, ConversationThreadParticipant
from foodsaving.groups.models import Group, GroupMembership
from foodsaving.users.models import User


@db_task()
def notify_participants(message):

    if message.reply_to:
        participants_to_notify = ConversationThreadParticipant.objects.filter(
            message=message.reply_to,
            muted=False,
        )
    else:
        participants_to_notify = ConversationParticipant.objects.filter(
            conversation=message.conversation,
            email_notifications=True,
        )

    participants_to_notify = participants_to_notify.exclude(
        user=message.author
    ).exclude(
        user__in=User.objects.unverified_or_ignored(),
    )

    # TODO: consider if we want to always send thread notifications even to inactive users
    if isinstance(message.conversation.target, Group):
        # if it's a group conversation, only send to users who are active in that group
        participants_to_notify = participants_to_notify.filter(
            user__groupmembership__in=GroupMembership.objects.active(),
            user__groupmembership__group=message.conversation.target,
        )

    for participant in participants_to_notify:
        try:
            foodsaving.conversations.emails.prepare_conversation_message_notification(user=participant.user,
                                                                                      message=message).send()
        except AnymailAPIError:
            sentry_client.captureException()
