import json

from channels import Channel
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from foodsaving.conversations.models import ConversationParticipant, ConversationMessage
from foodsaving.subscriptions.fcm import notify_multiple_devices
from foodsaving.subscriptions.models import ChannelSubscription, PushSubscription


@receiver(post_save, sender=ConversationMessage)
def send_messages(sender, instance, **kwargs):
    """When there is a message in a conversation we need to send it to any subscribed participants."""

    message = instance
    conversation = message.conversation

    # TODO: use a serializer
    topic = 'conversations:message'
    payload = {
        'id': message.id,
        'content': message.content,
        'author': message.author.id,
        'conversation': {
            'id': conversation.id
        }
    }

    push_exclude_users = []

    for subscription in ChannelSubscription.objects.filter(user__in=conversation.participants.all()):

        if not subscription.away_at:
            push_exclude_users.append(subscription.user)

        Channel(subscription.reply_channel).send({
            # TODO: use a serializer
            "text": json.dumps({
                'topic': topic,
                'payload': payload
            })
        })

    tokens = [item.token for item in
              PushSubscription.objects.filter(
                  Q(user__in=conversation.participants.all()) & ~Q(user__in=push_exclude_users) & ~Q(
                      user=message.author))]

    notify_multiple_devices(
        registration_ids=tokens,
        message_title=message.content,
        # this causes each notification for a given conversation to replace previous notifications so they don't build
        # up too much. fancier would be to make the new notifications show a summary not just the latest message.
        tag='conversation:{}'.format(conversation.id)
    )


@receiver(pre_delete, sender=ConversationParticipant)
def remove_participant(sender, instance, **kwargs):
    """When a user is removed from a conversation we will notify them."""

    user = instance.user
    conversation = instance.conversation
    for item in ChannelSubscription.objects.filter(user=user):
        Channel(item.reply_channel).send({
            # TODO: use a serializer
            'text': json.dumps({
                'topic': 'conversations:leave',
                'payload': {
                    'id': conversation.id
                }
            })
        })
