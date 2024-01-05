import logging
import os
from datetime import timedelta

import sentry_sdk
from anymail.exceptions import AnymailAPIError
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F, Q
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from karrot.conversations.emails import (
    prepare_conversation_message_notification,
    prepare_group_conversation_message_notification,
    prepare_mention_notification,
    prepare_place_conversation_message_notification,
)
from karrot.conversations.models import (
    Conversation,
    ConversationMessageAttachment,
    ConversationParticipant,
    ConversationThreadParticipant,
)
from karrot.users.models import User
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer

logger = logging.getLogger(__name__)


def get_participants_to_notify(message):
    if message.is_thread_reply():
        participants_to_notify = ConversationThreadParticipant.objects.filter(
            thread=message.thread,
            muted=False,
        ).filter(
            # Do not notify if thread participant doesn't have access to the conversation anymore
            # (We don't remove thread participants after they left the group)
            Q(thread__conversation__participants=F("user"))
            | Q(
                thread__conversation__group__groupmembership__user=F("user"),
                thread__conversation__group__isnull=False,
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

    return (
        participants_to_notify.exclude(
            user=message.author,
        )
        .exclude(
            user__in=User.objects.unverified(),
        )
        .exclude(
            seen_up_to__id__gte=message.id,
        )
        .exclude(
            notified_up_to__id__gte=message.id,
        )
        .distinct()
    )


def send_and_mark(participant, message, email):
    try:
        email.send()
    except AnymailAPIError:
        sentry_sdk.capture_exception()
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
        if target_type == "group":
            notify_group_conversation_participants(message)
            return

        if target_type == "place":
            notify_place_conversation_participants(message)
            return

        raise Exception(
            f'Conversation with target "{target_type}" supports threads,'
            f" but no notification template has been configured."
        )

    # skip this notification if this is not the most recent message, allows us to batch messages
    all_messages = conversation.messages
    if message.is_thread_reply():
        latest_message = all_messages.only_replies().latest("created_at")
    else:
        latest_message = all_messages.exclude_replies().latest("created_at")
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


@db_task()
def notify_mention(mention):
    email = prepare_mention_notification(mention)
    message = mention.message
    user = mention.user
    conversation = message.conversation
    participant = conversation.conversationparticipant_set.filter(user=user).first()
    if participant:
        if participant.notified_up_to_id and participant.notified_up_to_id >= message.id:
            # they've already read the message, so don't send out a notification
            return

        # they are in the conversation
        # we mark it, so we won't send out a normal message notification later
        send_and_mark(
            participant=participant,
            message=message,
            email=email,
        )
    else:
        email.send()


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

    stats_utils.periodic_task("conversations__mark_conversations_as_closed", seconds=t.elapsed_seconds)


@db_periodic_task(crontab(hour=4, minute=23))  # around 4am every day
def delete_orphaned_attachment_files():
    """Remove attachment files that are not longer present in the database

    Django does not do this automatically.

    See https://docs.djangoproject.com/en/4.2/ref/models/fields/#django.db.models.fields.files.FieldFile.delete

        "Note that when a model is deleted, related files are not deleted.
        If you need to cleanup orphaned files, you’ll need to handle it
        yourself (for instance, with a custom management command that can
        be run manually or scheduled to run periodically via e.g. cron)."

    """
    # this is an assumption that the default storage is being used
    storage = default_storage

    def walk(current_dir, field):
        try:
            dirs, file_names = storage.listdir(current_dir)

            # if it's empty, remove it
            if len(dirs) + len(file_names) == 0:
                storage.delete(current_dir)
                return

            for next_dir in dirs:
                walk(os.path.join(current_dir, next_dir), field)

            entries = {f"{current_dir}/{name}" for name in file_names}
            entries_in_use = set(
                ConversationMessageAttachment.objects.filter(**{f"{field}__in": entries}).values_list(field, flat=True)
            )
            entries_to_remove = entries.difference(entries_in_use)

            for name in entries_to_remove:
                created_time = storage.get_created_time(name)
                # just be cautious and only remove them if they are a bit older
                if created_time < timezone.now() - timedelta(minutes=5):
                    logger.info(f"Removing orphaned attachment {field}: {name}")
                    storage.delete(name)

            # check again
            dirs, file_names = storage.listdir(current_dir)

            # if it's empty, remove it
            if len(dirs) + len(file_names) == 0:
                storage.delete(current_dir)

        except FileNotFoundError:
            pass

    with timer() as t:
        # these have to match what is configured in the model
        walk("conversation_message_attachment_files", "file")
        walk("conversation_message_attachment_previews", "preview")
        walk("conversation_message_attachment_thumbnails", "thumbnail")

    stats_utils.periodic_task("conversations__delete_orphaned_attachment_files", seconds=t.elapsed_seconds)
