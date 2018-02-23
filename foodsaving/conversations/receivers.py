from email.utils import formataddr

from anymail.message import AnymailMessage
from django.conf import settings
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.conversations.models import ConversationParticipant, ConversationMessage
from foodsaving.webhooks.api import make_local_part
from foodsaving.webhooks.models import EmailEvent


@receiver(post_save, sender=ConversationMessage)
def mark_as_read(sender, instance, **kwargs):
    """Mark sent messages as read for the author"""

    message = instance
    participant = ConversationParticipant.objects.get(
        user=message.author,
        conversation=message.conversation
    )

    participant.seen_up_to = message
    participant.save()


@receiver(post_save, sender=ConversationMessage)
def notify_participants(sender, instance, **kwargs):
    message = instance

    participants_to_notify = ConversationParticipant.objects.filter(
        conversation=message.conversation,
        email_notifications=True
    ).exclude(
        user=message.author
    ).exclude(
        user__email__in=EmailEvent.objects.filter(event='bounce').values('address')
    )

    # TODO make into nice template
    for participant in participants_to_notify:
        local_part = make_local_part(message.conversation, participant.user)
        reply_to = formataddr(('Reply to Conversation', '{}@replies.karrot.world'.format(local_part)))
        AnymailMessage(
            subject='New conversation message from {}'.format(message.author.display_name),
            body=message.content,
            to=[participant.user.email],
            reply_to=[reply_to],
            from_email=settings.DEFAULT_FROM_EMAIL,
            track_clicks=False,
            track_opens=False
        ).send()


@receiver(post_save, sender=ConversationParticipant)
def set_conversation_updated_at_on_create(sender, instance, **kwargs):
    if kwargs['created']:
        participant = instance
        participant.conversation.save()


@receiver(pre_delete, sender=ConversationParticipant)
def set_conversation_updated_at_on_delete(sender, instance, **kwargs):
    participant = instance
    participant.conversation.save()
