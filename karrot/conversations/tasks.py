from anymail.exceptions import AnymailAPIError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Q, F
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_task, db_periodic_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from karrot.conversations.emails import (
    prepare_conversation_message_notification,
    prepare_group_conversation_message_notification,
    prepare_place_conversation_message_notification,
)
from karrot.conversations.models import ConversationParticipant, ConversationThreadParticipant, Conversation
from karrot.users.models import User
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


def get_participants_to_notify(message):
    if message.is_thread_reply():
        participants_to_notify = ConversationThreadParticipant.objects.filter(
            thread=message.thread,
            muted=False,
        ).filter(
            # Do not notify if thread participant doesn't have access to the conversation anymore
            # (We don't remove thread participants after they left the group)
            Q(thread__conversation__participants=F('user')) | Q(
                thread__conversation__group__groupmembership__user=F('user'),
                thread__conversation__is_group_public=True,
            )
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
    conversation = message.conversation

    # send individual notification emails for conversations that supports threads,
    # as replies via email will go into a thread
    if conversation.target and conversation.target.conversation_supports_threads and not message.is_thread_reply():
        target_type = conversation.type()
        if target_type == 'group':
            notify_group_conversation_participants(message)
            return

        if target_type == 'place':
            notify_place_conversation_participants(message)
            return

        raise Exception(
            f'Conversation with target "{target_type}" supports threads,'
            f' but no notification template has been configured.'
        )

    # skip this notification if this is not the most recent message, allows us to batch messages
    all_messages = conversation.messages
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
    with timer() as t:
        close_threshold = timezone.now() - relativedelta(days=settings.CONVERSATION_CLOSED_DAYS)
        for conversation in Conversation.objects.filter(
                is_closed=False,
                target_id__isnull=False,
        ).exclude(latest_message__created_at__gte=close_threshold):
            ended_at = conversation.target.ended_at
            if ended_at is not None and ended_at < close_threshold:
                conversation.is_closed = True
                conversation.save()

    stats_utils.periodic_task('conversations__mark_conversations_as_closed', seconds=t.elapsed_seconds)
