from anymail.exceptions import AnymailAPIError
from huey.contrib.djhuey import db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.conversations.emails import prepare_conversation_message_notification, \
    prepare_group_conversation_message_notification
from foodsaving.conversations.models import ConversationParticipant, ConversationThreadParticipant
from foodsaving.groups.models import GroupMembership
from foodsaving.users.models import User


def get_participants_to_notify(message):
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

    return participants_to_notify.exclude(
        user=message.author,
    ).exclude(
        user__in=User.objects.unverified_or_ignored(),
    ).exclude(
        seen_up_to__id__gte=message.id,
    ).exclude(
        notified_up_to__id__gte=message.id,
    ).distinct()


def send_and_mark(participant, message, email):
    try:
        email.send()
    except AnymailAPIError:
        sentry_client.captureException()
    else:
        participant.notified_up_to = message
        participant.save()


def notify_group_conversation_participants(message):
    # only send to users who are active in that group
    participants_to_notify = get_participants_to_notify(message).filter(
        user__groupmembership__in=GroupMembership.objects.active(),
        user__groupmembership__group=message.conversation.target,
    )

    for participant in participants_to_notify:
        email = prepare_group_conversation_message_notification(
            user=participant.user,
            message=message,
        )
        send_and_mark(
            participant=participant,
            message=message,
            email=email,
        )


@db_task()
def notify_participants(message):
    # send individual notification emails for group conversation message,
    # because replies via email will go into a thread
    if message.conversation.type() == 'group' and not message.is_thread_reply():
        notify_group_conversation_participants(message)
        return

    # skip this notification if this is not the most recent message, allows us to batch messages
    all_messages = message.conversation.messages
    if message.is_thread_reply():
        latest_message = all_messages.only_replies().latest('created_at')
    else:
        latest_message = all_messages.exclude_replies().latest('created_at')
    if latest_message.id != message.id:
        return

    for participant in get_participants_to_notify(message):
        messages = participant.unseen_and_unnotified_messages().all()
        email = prepare_conversation_message_notification(
            user=participant.user,
            messages=messages,
        )
        send_and_mark(
            participant=participant,
            message=message,
            email=email,
        )
