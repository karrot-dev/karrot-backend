import logging
from datetime import datetime

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from pytz import utc

from karrot.conversations import stats, tasks
from karrot.conversations.models import (
    ConversationMessage,
    ConversationMessageAttachment,
    ConversationMessageImage,
    ConversationMessageMention,
    ConversationMessageReaction,
    ConversationMeta,
    ConversationParticipant,
    ConversationThreadParticipant,
)
from karrot.notifications.models import Notification, NotificationType
from karrot.users.models import User
from karrot.utils.frontend_urls import message_url

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=ConversationMessage)
def create_thread_participant(sender, instance, **kwargs):
    message = instance

    if message.is_thread_reply():
        thread = message.thread
        if not thread.thread_id:
            # initialize thread
            thread.participants.create(user=thread.author)
            ConversationMessage.objects.filter(id=thread.id).update(thread=thread)
            thread.thread_id = thread.id

        if message.author != thread.author and not thread.participants.filter(user=message.author).exists():
            thread.participants.create(user=message.author)


@receiver(post_save, sender=ConversationMessage)
def mark_as_read(sender, instance, created, **kwargs):
    """Mark sent messages as read for the author"""
    message = instance

    if not created:
        return

    if message.is_thread_reply():
        participant = ConversationThreadParticipant.objects.get(
            user=message.author,
            thread=message.thread,
        )
    else:
        participant = ConversationParticipant.objects.get(user=message.author, conversation=message.conversation)

    participant.seen_up_to = message
    participant.save()


@receiver(post_save, sender=ConversationParticipant)
def mark_as_read_on_join(sender, instance, created, **kwargs):
    """When a user joins a conversation, we mark the latest message as the last seen.

    This makes joining new conversations less overwhelming for users since they are
    not presented with a potentially large backlog of unread messages.
    """

    if not created:
        return

    instance.seen_up_to = instance.conversation.latest_message
    instance.save()


@receiver(post_save, sender=ConversationMessage)
def notify_participants(sender, instance, created, **kwargs):
    message = instance

    if not created:
        return

    tasks.notify_participants.schedule(args=(message,), delay=5 * 60)


@receiver(post_save, sender=ConversationMessage)
def message_created(sender, instance, created, **kwargs):
    if not created:
        return
    stats.message_written(instance)


@receiver(post_save, sender=ConversationMessageReaction)
def reaction_created(sender, instance, created, **kwargs):
    if not created:
        return
    stats.reaction_given(instance)


@receiver(post_save, sender=ConversationMessageMention)
def user_mentioned(sender, instance, created, **kwargs):
    if not created:
        return

    mention = instance
    message = mention.message
    user = mention.user
    conversation = message.conversation

    if not conversation.supports_mentions():
        return

    if not conversation.group.is_member(user):
        # don't notify anyone who isn't in the group
        # we should not have created a mention though...
        return

    if user.id == message.author.id:
        # ignore self-mentions
        return

    # always give them a bell notification
    Notification.objects.create(
        type=NotificationType.MENTION.value,
        user=mention.user,
        context={
            "mention": mention.id,
            "group": conversation.group.id,
            "user": message.author.id,
            "url": message_url(message),
        },
    )

    if user.mail_verified:
        # verified mail is enough
        # we will notify inactive members here as maybe being mentioned draws them in again :)
        # 5 seconds delay so we don't notify them if they read it immediately
        tasks.notify_mention.schedule((mention,), delay=5)

    stats.user_mentioned(instance)


@receiver(pre_delete, sender=ConversationMessageMention)
def user_mention_deleted(sender, instance, **kwargs):
    mention = instance
    Notification.objects.filter(type=NotificationType.MENTION.value, context__mention=mention.id).delete()


@receiver(post_save, sender=ConversationParticipant)
def set_conversation_updated_at_on_create(sender, instance, created, **kwargs):
    if created:
        participant = instance
        participant.conversation.save()


@receiver(pre_delete, sender=ConversationParticipant)
def set_conversation_updated_at_on_delete(sender, instance, **kwargs):
    participant = instance
    participant.conversation.save()


@receiver(post_save, sender=User)
def make_conversation_meta(sender, instance, created, **kwargs):
    if not created:
        return

    user = instance
    # This is equivalent of not setting marked_at, by choosing a the earliest date possible
    # (but it has to be timezone-aware, otherwise there will be comparison errors)
    min_date = datetime.min.replace(tzinfo=utc)
    ConversationMeta.objects.get_or_create(
        {
            "conversations_marked_at": min_date,
            "threads_marked_at": min_date,
        },
        user=user,
    )


@receiver(post_delete, sender=ConversationMessageImage)
def delete_message_image_files(sender, instance, **kwargs):
    instance.image.delete_all_created_images()
    instance.image.delete(save=False)


@receiver(post_delete, sender=ConversationMessageAttachment)
def delete_message_attachment_files(sender, instance, **kwargs):
    for file in [instance.file, instance.preview, instance.thumbnail]:
        if file:
            try:
                file.delete(save=False)
            except Exception as ex:  # noqa: BLE001
                logger.error(ex)
