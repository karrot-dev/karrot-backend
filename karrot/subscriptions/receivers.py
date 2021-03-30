from collections import defaultdict

from itertools import groupby

from django.conf import settings
from django.contrib.auth import user_logged_out
from django.db.models import Q
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver

from karrot.applications.models import Application
from karrot.applications.serializers import ApplicationSerializer
from karrot.community_feed.models import CommunityFeedMeta
from karrot.community_feed.serializers import CommunityFeedMetaSerializer
from karrot.conversations.models import ConversationParticipant, ConversationMessage, ConversationMessageReaction, \
    ConversationThreadParticipant, ConversationMeta
from karrot.conversations.serializers import ConversationMessageSerializer, ConversationSerializer, \
    ConversationMetaSerializer
from karrot.conversations.signals import thread_marked_seen, new_conversation_message, new_thread_message, \
    conversation_marked_seen
from karrot.groups.models import Group, Trust, GroupMembership
from karrot.groups.serializers import GroupDetailSerializer, GroupPreviewSerializer
from karrot.history.models import history_created
from karrot.history.serializers import HistorySerializer
from karrot.invitations.models import Invitation
from karrot.invitations.serializers import InvitationSerializer
from karrot.issues.serializers import IssueSerializer
from karrot.issues.signals import issue_changed
from karrot.notifications.models import Notification, NotificationMeta
from karrot.notifications.serializers import NotificationSerializer, NotificationMetaSerializer
from karrot.offers.models import Offer, OfferStatus
from karrot.offers.serializers import OfferSerializer
from karrot.activities.models import Activity, ActivitySeries, Feedback, ActivityParticipant, ActivityType
from karrot.activities.serializers import ActivitySerializer, ActivitySeriesSerializer, FeedbackSerializer, \
    ActivityTypeSerializer
from karrot.places.models import Place, PlaceSubscription
from karrot.places.serializers import PlaceSerializer
from karrot.status.helpers import unseen_notification_count, unread_conversations, pending_applications, \
    get_feedback_possible
from karrot.subscriptions import tasks
from karrot.subscriptions.models import ChannelSubscription
from karrot.subscriptions.utils import send_in_channel, MockRequest
from karrot.userauth.serializers import AuthUserSerializer
from karrot.users.serializers import UserSerializer
from karrot.utils.misc import on_transaction_commit


@receiver(post_save, sender=ConversationMessage)
@on_transaction_commit
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
        participant = conversation.conversationparticipant_set.get(user=subscription.user)
        payload = ConversationSerializer(participant, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationParticipant)
def send_conversation_update(sender, instance, **kwargs):
    # Update conversations object for user after updating their participation
    # (important for seen_up_to and unread_message_count)
    participant = instance

    topic = 'conversations:conversation'
    payload = ConversationSerializer(participant, context={'request': MockRequest(user=participant.user)}).data

    for subscription in ChannelSubscription.objects.recent().filter(user=instance.user):
        send_in_channel(subscription.reply_channel, topic, payload)


@receiver(post_save, sender=ConversationMeta)
def conversation_meta_saved(sender, instance, **kwargs):
    meta = instance
    payload = ConversationMetaSerializer(meta).data
    for subscription in ChannelSubscription.objects.recent().filter(user=meta.user):
        send_in_channel(subscription.reply_channel, topic='conversations:meta', payload=payload)


@receiver(post_save, sender=ConversationThreadParticipant)
@on_transaction_commit
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
@on_transaction_commit
def send_reaction_update(sender, instance, **kwargs):
    reaction = instance
    message = reaction.message
    conversation = message.conversation

    topic = 'conversations:message'

    for subscription in ChannelSubscription.objects.recent() \
            .filter(user__in=conversation.participants.all()).distinct():
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
        participant = conversation.conversationparticipant_set.get(user=subscription.user)
        payload = ConversationSerializer(participant, context={'request': MockRequest(user=subscription.user)}).data
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
    """Notify conversation participants when someone leaves"""
    conversation = instance.conversation

    topic = 'conversations:conversation'

    # TODO send to all group members?

    for subscription in ChannelSubscription.objects.recent() \
            .filter(user__in=conversation.participants.all()).distinct():
        participant = conversation.conversationparticipant_set.get(user=subscription.user)
        payload = ConversationSerializer(participant, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic, payload)

    participant = conversation.make_participant()
    payload = ConversationSerializer(participant).data
    for subscription in ChannelSubscription.objects.recent().filter(user=instance.user).distinct():
        send_in_channel(subscription.reply_channel, topic, payload)


# Group
def send_group_detail(group, user=None):
    qs = ChannelSubscription.objects.recent().distinct()
    if user:
        qs = qs.filter(user=user)
    else:
        qs = qs.filter(user__in=group.members.all())

    for subscription in qs:
        payload = GroupDetailSerializer(group, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='groups:group_detail', payload=payload)


def send_group_preview(group):
    preview_payload = GroupPreviewSerializer(group).data
    for subscription in ChannelSubscription.objects.recent():
        send_in_channel(subscription.reply_channel, topic='groups:group_preview', payload=preview_payload)


@receiver(post_save, sender=Group)
def send_group_updates(sender, instance, **kwargs):
    group = instance

    # avoid websocket updates if the change isn't visible to users
    dirty_fields = group.get_dirty_fields()
    if len(dirty_fields) == 1 and 'last_active_at' in dirty_fields:
        return

    send_group_detail(group)
    send_group_preview(group)


# GroupMembership
@receiver(post_save, sender=GroupMembership)
def send_group_membership_updates(sender, instance, created, **kwargs):
    membership = instance
    group = membership.group

    dirty_fields = membership.get_dirty_fields()

    # Send updates if the membership was created or roles changed
    if created or 'roles' in dirty_fields.keys():
        send_group_detail(group)
    elif 'notification_types' in dirty_fields.keys():
        # notification types are only visible to one user
        send_group_detail(group, user=membership.user)

    if created:
        send_group_preview(group)


@receiver(post_delete, sender=GroupMembership)
def send_group_member_left(sender, instance, **kwargs):
    group = instance.group
    send_group_detail(group)
    send_group_preview(group)


# Applications
@receiver(post_save, sender=Application)
def send_application_updates(sender, instance, **kwargs):
    application = instance
    group = application.group
    payload = ApplicationSerializer(application).data
    q = Q(user__in=group.members.all()) | Q(user=application.user)
    for subscription in ChannelSubscription.objects.recent().filter(q).distinct():
        send_in_channel(subscription.reply_channel, topic='applications:update', payload=payload)


# Trust
@receiver(post_save, sender=Trust)
def send_trust_updates(sender, instance, **kwargs):
    send_group_updates(sender, instance.membership.group)


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


# Place
@receiver(post_save, sender=Place)
def send_place_updates(sender, instance, **kwargs):
    place = instance
    for subscription in ChannelSubscription.objects.recent().filter(user__in=place.group.members.all()).distinct():
        payload = PlaceSerializer(place, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='places:place', payload=payload)


@receiver(post_save, sender=PlaceSubscription)
@receiver(post_delete, sender=PlaceSubscription)
def place_subscription_updated(sender, instance, **kwargs):
    place = instance.place
    user = instance.user
    payload = PlaceSerializer(place, context={'request': MockRequest(user=user)}).data
    for subscription in ChannelSubscription.objects.recent().filter(user=user).distinct():
        send_in_channel(subscription.reply_channel, topic='places:place', payload=payload)


# Activities
@receiver(post_save, sender=Activity)
def send_activity_updates(sender, instance, **kwargs):
    activity = instance
    if activity.is_done:
        # doesn't change serialized data
        return

    payload = ActivitySerializer(activity).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=activity.place.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:activity', payload=payload)


@receiver(pre_delete, sender=Activity)
def send_activity_deleted(sender, instance, **kwargs):
    activity = instance
    payload = ActivitySerializer(activity).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=activity.place.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:activity_deleted', payload=payload)


@receiver(post_save, sender=ActivityParticipant)
@receiver(post_delete, sender=ActivityParticipant)
def send_activity_participant_updates(sender, instance, **kwargs):
    activity = instance.activity
    payload = ActivitySerializer(activity).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=activity.place.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:activity', payload=payload)


# Activity Series
@receiver(post_save, sender=ActivitySeries)
def send_activity_series_updates(sender, instance, **kwargs):
    series = instance
    payload = ActivitySeriesSerializer(series).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=series.place.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:series', payload=payload)


@receiver(pre_delete, sender=ActivitySeries)
def send_activity_series_delete(sender, instance, **kwargs):
    series = instance
    payload = ActivitySeriesSerializer(series).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=series.place.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:series_deleted', payload=payload)


# Activity Type
@receiver(post_save, sender=ActivityType)
def send_activity_type_updates(sender, instance, **kwargs):
    activity_type = instance
    payload = ActivityTypeSerializer(activity_type).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=activity_type.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:type', payload=payload)


@receiver(pre_delete, sender=ActivityType)
def send_activity_type_delete(sender, instance, **kwargs):
    activity_type = instance
    payload = ActivityTypeSerializer(activity_type).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=activity_type.group.members.all()
                                                                    ).distinct():
        send_in_channel(subscription.reply_channel, topic='activities:type_deleted', payload=payload)


# Offer
@receiver(post_save, sender=Offer)
def send_offer_updates(sender, instance, created, **kwargs):
    offer = instance
    payload = OfferSerializer(offer).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=offer.group.members.all()).distinct():
        if offer.status == OfferStatus.ACTIVE.value or \
           offer.user == subscription.user or \
           subscription.user.conversation_set.filter(id=offer.conversation.id).exists():
            send_in_channel(subscription.reply_channel, topic='offers:offer', payload=payload)
        elif not created:
            # if the user cannot see it, it's deleted from their point of view!
            send_in_channel(subscription.reply_channel, topic='offers:offer_deleted', payload=payload)

    if created:
        tasks.notify_new_offer_push_subscribers(offer)


@receiver(pre_delete, sender=Offer)
def send_offer_delete(sender, instance, **kwargs):
    offer = instance
    payload = OfferSerializer(offer).data
    for subscription in ChannelSubscription.objects.recent().filter(user__in=offer.group.members.all()).distinct():
        send_in_channel(subscription.reply_channel, topic='offers:offer_deleted', payload=payload)


# Feedback
@receiver(post_save, sender=Feedback)
def send_feedback_updates(sender, instance, **kwargs):
    feedback = instance
    for subscription in ChannelSubscription.objects.recent().filter(user__in=feedback.about.place.group.members.all()
                                                                    ).distinct():
        payload = FeedbackSerializer(feedback, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='feedback:feedback', payload=payload)


# Users
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def send_auth_user_updates(sender, instance, **kwargs):
    """Send full details to the user"""
    user = instance
    payload = AuthUserSerializer(user, context={'request': MockRequest(user=user)}).data
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
    payload = UserSerializer(user, context={'request': MockRequest()}).data
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


# Issue
@receiver(issue_changed)
def send_issue_updates(sender, issue, **kwargs):
    for subscription in ChannelSubscription.objects.recent().filter(user__groupmembership__group=issue.group
                                                                    ).distinct():
        payload = IssueSerializer(issue, context={'request': MockRequest(user=subscription.user)}).data
        send_in_channel(subscription.reply_channel, topic='issues:issue', payload=payload)


# Community Feed
@receiver(post_save, sender=CommunityFeedMeta)
def community_feed_meta_saved(sender, instance, **kwargs):
    meta = instance
    payload = CommunityFeedMetaSerializer(meta).data
    for subscription in ChannelSubscription.objects.recent().filter(user=meta.user):
        send_in_channel(subscription.reply_channel, topic='community_feed:meta', payload=payload)


# Status
def send_conversation_status_update(subscriptions, changed_conversation=None):
    for user, subscriptions in groupby(sorted(list(subscriptions), key=lambda x: x.user.id), key=lambda x: x.user):
        payload = unread_conversations(user)

        if changed_conversation:
            # We know that something about this conversation has been changed
            # It might be all messages are read and we need to tell the client this
            # Hence, set unread_wall_message_count to 0 if there are no unread messages for that conversation
            target_id = changed_conversation.target_id
            t = changed_conversation.type()
            if t == 'group' and target_id not in payload['groups']:
                payload['groups'][target_id] = {'unread_wall_message_count': 0}
            elif t == 'place' and target_id not in payload['places']:
                payload['places'][target_id] = {'unread_wall_message_count': 0}

        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic='status', payload=payload)


@receiver(new_conversation_message)
def new_conversation_message_to_status(sender, message, **kwargs):
    conversation = message.conversation
    send_conversation_status_update(
        ChannelSubscription.objects.recent().filter(user__in=conversation.participants.all()
                                                    ).exclude(user=conversation.latest_message.author).distinct(),
    )


@receiver(new_thread_message)
def new_thread_message_to_status(sender, message, **kwargs):
    thread = message.thread
    send_conversation_status_update(
        ChannelSubscription.objects.recent().filter(user__in=thread.conversation.participants.all()
                                                    ).exclude(user=thread.latest_message.author).distinct(),
    )


@receiver(post_save, sender=ConversationMeta)
def conversation_participant_saved(sender, instance, **kwargs):
    # user opened the latest messages menu
    meta = instance
    send_conversation_status_update(ChannelSubscription.objects.recent().filter(user=meta.user))


@receiver(conversation_marked_seen)
def conversation_marked_seen_to_status(sender, participant, **kwargs):
    conversation = participant.conversation
    send_conversation_status_update(
        ChannelSubscription.objects.recent().filter(user=participant.user).distinct(),
        changed_conversation=conversation,
    )


@receiver(thread_marked_seen)
def conversation_thread_marked_to_status(sender, participant, **kwargs):
    send_conversation_status_update(ChannelSubscription.objects.recent().filter(user=participant.user).distinct())


@receiver(post_delete, sender=ConversationParticipant)
def conversation_participant_deleted(sender, instance, **kwargs):
    # user unsubscribed from the conversation
    participant = instance

    send_conversation_status_update(
        ChannelSubscription.objects.recent().filter(user=participant.user),
        changed_conversation=participant.conversation,
    )


def send_notification_status_update(user):
    count = unseen_notification_count(user)
    for subscription in ChannelSubscription.objects.recent().filter(user=user):
        send_in_channel(
            subscription.reply_channel, topic='status', payload={
                'unseen_notification_count': count,
            }
        )


@receiver(post_save, sender=Notification)
@receiver(post_delete, sender=Notification)
def notification_changed(sender, instance, **kwargs):
    notification = instance
    send_notification_status_update(user=notification.user)


@receiver(post_save, sender=NotificationMeta)
def notification_meta_to_status(sender, instance, **kwargs):
    notification_meta = instance
    send_notification_status_update(user=notification_meta.user)


@receiver(post_save, sender=Application)
def application_saved(sender, instance, **kwargs):
    application = instance
    for user, subscriptions in groupby(sorted(list(
            ChannelSubscription.objects.recent().filter(user__in=application.group.members.all())),
                                              key=lambda x: x.user.id), key=lambda x: x.user):

        groups = defaultdict(dict)
        for group_id, count in pending_applications(user):
            groups[group_id]['pending_application_count'] = count

        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic='status', payload={'groups': groups})


@receiver(post_save, sender=Activity)
def activity_date_saved(sender, instance, **kwargs):
    activity = instance

    if activity.is_done is False:
        # Activity is not done
        return
    # TODO don't send if 'is_done' did not change

    for user, subscriptions in groupby(sorted(list(
            ChannelSubscription.objects.recent().filter(user__in=activity.participants.all())),
                                              key=lambda x: x.user.id), key=lambda x: x.user):

        groups = defaultdict(dict)
        for group_id, count in get_feedback_possible(user):
            groups[group_id]['feedback_possible_count'] = count

        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic='status', payload={'groups': groups})


@receiver(post_save, sender=Feedback)
def feedback_saved(sender, instance, created, **kwargs):
    feedback = instance

    if not created:
        return

    user = feedback.given_by

    send_feedback_possible_count(user)


@receiver(post_save, sender=ActivityParticipant)
def activity_participant_saved(sender, instance, **kwargs):
    activity_participant = instance

    user = activity_participant.user

    send_feedback_possible_count(user)


def send_feedback_possible_count(user):
    groups = defaultdict(dict)

    for group_id, count in get_feedback_possible(user):
        groups[group_id]['feedback_possible_count'] = count

    payload = {'groups': groups}

    for subscription in ChannelSubscription.objects.recent().filter(user=user):
        send_in_channel(subscription.reply_channel, topic='status', payload=payload)
