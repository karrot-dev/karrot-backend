from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.conversations import tasks, stats
from foodsaving.conversations.models import (
    ConversationParticipant,
    ConversationMessage,
    ConversationMessageReaction,
    ConversationThreadParticipant,
)


@receiver(post_save, sender=ConversationMessage)
def create_thread_participant(sender, instance, created, **kwargs):
    if not created:
        return
    message = instance
    thread = message.thread

    if thread:
        if not thread.thread_id:
            # initialize thread
            thread.participants.create(user=thread.author)
            thread.thread_id = thread.id
            thread.save()

        if message.author != thread.author and not thread.participants.filter(user=message.author).exists():
            thread.participants.create(user=message.author)


@receiver(post_save, sender=ConversationMessage)
def mark_as_read(sender, instance, **kwargs):
    """Mark sent messages as read for the author"""

    message = instance

    if message.thread:
        participant = ConversationThreadParticipant.objects.get(
            user=message.author,
            thread=message.thread,
        )
    else:
        participant = ConversationParticipant.objects.get(
            user=message.author,
            conversation=message.conversation
        )

    # When a message is updated, the participants seen_up_to
    # member variable gets set to that updated message. Perform the below
    # check to ensure this does not occur.
    if participant.seen_up_to:
        if participant.seen_up_to.id < message.id:
            participant.seen_up_to = message
    else:
        participant.seen_up_to = message

    participant.save()


@receiver(post_save, sender=ConversationMessage)
def notify_participants(sender, instance, created, **kwargs):
    message = instance

    if not created:
        return

    tasks.notify_participants(message)


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


@receiver(post_save, sender=ConversationParticipant)
def set_conversation_updated_at_on_create(sender, instance, created, **kwargs):
    if created:
        participant = instance
        participant.conversation.save()


@receiver(pre_delete, sender=ConversationParticipant)
def set_conversation_updated_at_on_delete(sender, instance, **kwargs):
    participant = instance
    participant.conversation.save()
