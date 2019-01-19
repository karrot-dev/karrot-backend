from collections import namedtuple

import json
from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import user_logged_out
from django.db.models import Q
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.applications.models import GroupApplication
from foodsaving.applications.serializers import GroupApplicationSerializer
from foodsaving.cases.models import GroupCase, Voting, Option, Vote
from foodsaving.cases.serializers import ConflictResolutionSerializer
from foodsaving.conversations.models import ConversationParticipant, ConversationMessage, ConversationMessageReaction, \
    ConversationThreadParticipant
from foodsaving.conversations.serializers import ConversationMessageSerializer, ConversationSerializer
from foodsaving.groups.models import Group, Trust, GroupMembership
from foodsaving.groups.serializers import GroupDetailSerializer, GroupPreviewSerializer
from foodsaving.history.models import history_created
from foodsaving.history.serializers import HistorySerializer
from foodsaving.invitations.models import Invitation
from foodsaving.invitations.serializers import InvitationSerializer
from foodsaving.notifications.models import Notification, NotificationMeta
from foodsaving.notifications.serializers import NotificationSerializer, NotificationMetaSerializer
from foodsaving.pickups.models import PickupDate, PickupDateSeries, Feedback, PickupDateCollector
from foodsaving.pickups.serializers import PickupDateSerializer, PickupDateSeriesSerializer, FeedbackSerializer
from foodsaving.stores.models import Store
from foodsaving.stores.serializers import StoreSerializer
from foodsaving.subscriptions import stats, tasks
from foodsaving.subscriptions.models import ChannelSubscription
from foodsaving.userauth.serializers import AuthUserSerializer
from foodsaving.users.serializers import UserSerializer

MockRequest = namedtuple('Request', ['user'])


class AbsoluteURIBuildingRequest:
    def build_absolute_uri(self, path):
        return settings.HOSTNAME + path


channel_layer = get_channel_layer()
channel_layer_send_sync = async_to_sync(channel_layer.send)


def send_in_channel(channel, topic, payload):
    message = {
        'type': 'message.send',
        'text': json.dumps({
            'topic': topic,
            'payload': payload,
        }),
    }
    try:
        channel_layer_send_sync(channel, message)
    except ChannelFull:
        # maybe this means the subscription is invalid now?
        sentry_client.captureException()
    else:
        stats.pushed_via_websocket(topic)


@receiver(post_save, sender=ConversationMessage)
def send_messages(sender, instance, created, **kwargs):
    """When there is a message in a conversation we need to send it to any subscribed participants."""
    message = instance
    conversation = message.conversation

    topic = 'conversations:message'

    for subscription in ChannelSubscription.objects.recent().filter(user__in=conversation.participants.all()
                                                                    ).distinct():

        payload = ConversationMessageSerializer(message, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)

        if created and message.is_thread_reply() and subscription.user != message.author:
            payload = ConversationMessageSerializer(
                message.thread, context={
                    'request': MockRequest(user=subscription.user)
                }
            ).data
            send_in_channel(subscription.reply_channel, topic, payload)

    # Send push notification and conversation updates when a message is created, but not when it is modified
    if not created:
        return

    tasks.notify_message_push_subscribers(message)

    # Send conversations object to participants after sending a message
    # (important for unread_message_count)
    # Exclude the author because their seen_up_to status gets updated,
    # so they will receive the `send_conversation_update` message
    topic = 'conversations:conversation'

    # Can be skipped for thread replies, as they don't alter the conversations object
    if message.is_thread_reply():
        return

    for subscription in ChannelSubscription.objects.recent()\
            .filter(user__in=conversation.participants.all())\
            .exclude(user=message.author).distinct():
        payload = ConversationSerializer(conversation, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationParticipant)
def send_conversation_update(sender, instance, **kwargs):
    # Update conversations object for user after updating their participation
    # (important for seen_up_to and unread_message_count)
    conversation = instance.conversation

    topic = 'conversations:conversation'
    payload = ConversationSerializer(conversation, context={'request': MockRequest(user=instance.user)}).data

    for subscription in ChannelSubscription.objects.recent().filter(user=instance.user):
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationThreadParticipant)
def send_thread_update(sender, instance, created, **kwargs):
    # Update thread object for user after updating their participation
    # (important for seen_up_to and unread_message_count)

    # Saves a few unnecessary messages if we only send on modify
    if created:
        return

    thread = instance.thread

    topic = 'conversations:message'
    payload = ConversationMessageSerializer(thread, context={'request': MockRequest(user=instance.user)}).data

    for subscription in ChannelSubscription.objects.recent().filter(user=instance.user):
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationMessageReaction)
@receiver(post_delete, sender=ConversationMessageReaction)
def send_reaction_update(sender, instance, **kwargs):
    reaction = instance
    message = reaction.message
    conversation = message.conversation

    topic = 'conversations:message'

    for subscription in ChannelSubscription.objects.recent() \
            .filter(user__in=conversation.participants.all()) \
            .exclude(user=reaction.user).distinct():
        payload = ConversationMessageSerializer(message, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationParticipant)
def send_participant_joined(sender, instance, created, **kwargs):
    """Notify other participants when someone joins"""
    if not created:
        return

    conversation = instance.conversation

    topic = 'conversations:conversation'

    for subscription in ChannelSubscription.objects.recent() \
            .filter(user__in=conversation.participants.all()) \
            .exclude(user=instance.user).distinct():
        payload = ConversationSerializer(conversation, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(pre_delete, sender=ConversationParticipant)
def remove_participant(sender, instance, **kwargs):
    """When a user is removed from a conversation we will notify them."""

    user = instance.user
    conversation = instance.conversation
    for subscription in ChannelSubscription.objects.recent().filter(user=user):
        send_in_channel(subscription.reply_channel, topic='conversations:leave', payload={'id': conversation.id})


@receiver(post_delete, sender=ConversationParticipant)
def send_participant_left(sender, instance, **kwargs):
    """Notify other conversation participants when someone leaves"""
    conversation = instance.conversation

    topic = 'conversations:conversation'

    for subscription in ChannelSubscription.objects.recent() \
            .filter(user__in=conversation.participants.all()) \
            .exclude(user=instance.user).distinct():
        payload = ConversationSerializer(conversation, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)


# Group
@receiver(post_save, sender=Group)
def send_group_updates(sender, instance, **kwargs):
    group = instance
    detail_payload = GroupDetailSerializer(group).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=group.members.all()).distinct():
        send_in_channel(subscription.reply_channel, topic='groups:group_detail', payload=detail_payload)

    preview_payload = GroupPreviewSerializer(group).data
    for subscription in ChannelSubscription.objects.recent():
        send_in_channel(subscription.reply_channel, topic='groups:group_preview', payload=preview_payload)


# GroupMembership
@receiver(post_save, sender=GroupMembership)
def send_group_membership_updates(sender, instance, created, **kwargs):
    group = instance.group
    if not created:
        return
    send_group_updates(sender, group)


@receiver(post_delete, sender=GroupMembership)
def send_group_member_left(sender, instance, **kwargs):
    group = instance.group
    send_group_updates(sender, group)


# Applications
@receiver(post_save, sender=GroupApplication)
def send_group_application_updates(sender, instance, **kwargs):
    application = instance
    group = application.group
    payload = GroupApplicationSerializer(application).data
    q = Q(user__in=group.members.all()) | Q(user=application.user)
    for subscription in ChannelSubscription.objects.recent().filter(q).distinct():
        send_in_channel(subscription.reply_channel, topic='applications:update', payload=payload)


# Trust
@receiver(post_save, sender=Trust)
def send_trust_updates(sender, instance, **kwargs):
    send_group_updates(sender, instance.membership.group)
    send_user_updates(sender, instance.membership.user)  # TODO check if needed


# Invitations
@receiver(post_save, sender=Invitation)
def send_invitation_updates(sender, instance, **kwargs):
    invitation = instance
    payload = InvitationSerializer(invitation).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=invitation.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='invitations:invitation', payload=payload)


@receiver(pre_delete, sender=Invitation)
def send_invitation_accept(sender, instance, **kwargs):
    invitation = instance
    payload = InvitationSerializer(invitation).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=invitation.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='invitations:invitation_accept', payload=payload)


# Store
@receiver(post_save, sender=Store)
def send_store_updates(sender, instance, **kwargs):
    store = instance
    payload = StoreSerializer(store).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=store.group.members.all()).distinct():
        send_in_channel(subscription.reply_channel, topic='stores:store', payload=payload)


# Pickup Dates
@receiver(post_save, sender=PickupDate)
def send_pickup_updates(sender, instance, **kwargs):
    pickup = instance
    if pickup.feedback_possible:
        # doesn't change serialized data
        return

    payload = PickupDateSerializer(pickup).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=pickup.store.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='pickups:pickupdate', payload=payload)


@receiver(pre_delete, sender=PickupDate)
def send_pickup_deleted(sender, instance, **kwargs):
    pickup = instance
    payload = PickupDateSerializer(pickup).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=pickup.store.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='pickups:pickupdate_deleted', payload=payload)


@receiver(post_save, sender=PickupDateCollector)
@receiver(post_delete, sender=PickupDateCollector)
def send_pickup_collector_updates(sender, instance, **kwargs):
    pickup = instance.pickupdate
    payload = PickupDateSerializer(pickup).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=pickup.store.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='pickups:pickupdate', payload=payload)


# Pickup Date Series
@receiver(post_save, sender=PickupDateSeries)
def send_pickup_series_updates(sender, instance, **kwargs):
    series = instance
    payload = PickupDateSeriesSerializer(series).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=series.store.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='pickups:series', payload=payload)


@receiver(pre_delete, sender=PickupDateSeries)
def send_pickup_series_delete(sender, instance, **kwargs):
    series = instance
    payload = PickupDateSeriesSerializer(series).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=series.store.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='pickups:series_deleted', payload=payload)


# Feedback
@receiver(post_save, sender=Feedback)
def send_feedback_updates(sender, instance, **kwargs):
    feedback = instance
    for subscription in ChannelSubscription.objects.recent().filter(user__in=feedback.about.store.group.members.all()
                                                                    ).distinct():
        payload = FeedbackSerializer(feedback, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='feedback:feedback', payload=payload)


# Users
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def send_auth_user_updates(sender, instance, **kwargs):
    """Send full details to the user"""
    user = instance
    payload = AuthUserSerializer(user, context={'request': AbsoluteURIBuildingRequest()}).data
    for subscription in ChannelSubscription.objects.recent().filter(user=user):
        send_in_channel(subscription.reply_channel, topic='auth:user', payload=payload)


@receiver(user_logged_out)
def notify_logged_out_user(sender, user, **kwargs):
    for subscription in ChannelSubscription.objects.recent().filter(user=user):
        send_in_channel(subscription.reply_channel, topic='auth:logout', payload={})


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def send_user_updates(sender, instance, **kwargs):
    """Send profile updates to everyone except the user"""
    user = instance
    payload = UserSerializer(user, context={'request': AbsoluteURIBuildingRequest()}).data
    user_groups = user.groups.values('id')
    for subscription in ChannelSubscription.objects.recent().filter(user__groups__in=user_groups).exclude(user=user
                                                                                                          ).distinct():
        send_in_channel(subscription.reply_channel, topic='users:user', payload=payload)


# History
@receiver(history_created)
def send_history_updates(sender, instance, **kwargs):
    history = instance
    payload = HistorySerializer(history).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=history.group.members.all()).distinct():
        send_in_channel(subscription.reply_channel, topic='history:history', payload=payload)


# Notification
@receiver(post_save, sender=Notification)
def notification_saved(sender, instance, **kwargs):
    notification = instance
    payload = NotificationSerializer(notification).data
    for subscription in ChannelSubscription.objects.recent().filter(user=notification.user):
        send_in_channel(subscription.reply_channel, topic='notifications:notification', payload=payload)


@receiver(pre_delete, sender=Notification)
def notification_deleted(sender, instance, **kwargs):
    notification = instance
    payload = NotificationSerializer(notification).data
    for subscription in ChannelSubscription.objects.recent().filter(user=notification.user):
        send_in_channel(subscription.reply_channel, topic='notifications:notification_deleted', payload=payload)


@receiver(post_save, sender=NotificationMeta)
def notification_meta_saved(sender, instance, **kwargs):
    meta = instance
    payload = NotificationMetaSerializer(meta).data
    for subscription in ChannelSubscription.objects.recent().filter(user=meta.user):
        send_in_channel(subscription.reply_channel, topic='notifications:meta', payload=payload)


# GroupCase
def send_case_updates(case):
    for subscription in ChannelSubscription.objects.recent().filter(user__caseparticipant__case=case).distinct():
        payload = ConflictResolutionSerializer(case, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='cases:case', payload=payload)


@receiver(post_save, sender=GroupCase)
def case_saved(sender, instance, **kwargs):
    send_case_updates(instance)


@receiver(post_save, sender=Voting)
def voting_saved(sender, instance, **kwargs):
    send_case_updates(instance.case)


@receiver(post_save, sender=Option)
def option_saved(sender, instance, **kwargs):
    send_case_updates(instance.voting.case)


@receiver(pre_delete, sender=Vote)
@receiver(post_save, sender=Vote)
def vote_saved(sender, instance, **kwargs):
    send_case_updates(instance.option.voting.case)
