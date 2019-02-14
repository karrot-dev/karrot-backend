from anymail.exceptions import AnymailAPIError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_task, db_periodic_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.conversations.emails import (
    prepare_conversation_message_notification,
    prepare_group_conversation_message_notification,
    prepare_place_conversation_message_notification,
)
from foodsaving.conversations.models import ConversationParticipant, ConversationThreadParticipant, Conversation
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
            muted=False,
        )

    group = message.conversation.find_group()
    if group is not None:
        # prevent sending emails to inactive group members, but still send to non-members (e.g. for applicants)
        active_members = Q(user__groupmembership__inactive_at__isnull=True, user__groupmembership__group=group)
        not_in_group = ~Q(user__groupmembership__group=group)
        participants_to_notify = participants_to_notify.filter(active_members | not_in_group)

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
    for participant in get_participants_to_notify(message):
        email = prepare_group_conversation_message_notification(
            user=participant.user,
            message=message,
        )
        send_and_mark(
            participant=participant,
            message=message,
            email=email,
        )


def notify_place_conversation_participants(message):
    for participant in get_participants_to_notify(message):
        email = prepare_place_conversation_message_notification(
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

    if message.conversation.type() == 'place' and not message.is_thread_reply():
        notify_place_conversation_participants(message)
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


@db_periodic_task(crontab(hour=3, minute=9))  # around 3am every day
def mark_conversations_as_closed():
    close_threshold = timezone.now() - relativedelta(days=settings.CONVERSATION_CLOSED_DAYS)
    for conversation in Conversation.objects.filter(
            is_closed=False,
            latest_message__created_at__lt=close_threshold,
            target_id__isnull=False,
    ):
        if conversation.target.has_ended:
            conversation.is_closed = True
            conversation.save()
