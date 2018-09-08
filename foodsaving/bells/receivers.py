from collections import namedtuple

import json
from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import user_logged_out
from django.db.models import Q
from django.db.models.signals import post_save, pre_delete, m2m_changed, post_delete, pre_save
from django.dispatch import receiver
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.applications.models import GroupApplication, GroupApplicationStatus
from foodsaving.applications.serializers import GroupApplicationSerializer
from foodsaving.bells.models import Bell, BellType
from foodsaving.conversations.models import ConversationParticipant, ConversationMessage, ConversationMessageReaction, \
    ConversationThreadParticipant
from foodsaving.conversations.serializers import ConversationMessageSerializer, ConversationSerializer
from foodsaving.groups.models import Group, Trust, GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.groups.serializers import GroupDetailSerializer, GroupPreviewSerializer
from foodsaving.history.models import history_created
from foodsaving.history.serializers import HistorySerializer
from foodsaving.invitations.models import Invitation
from foodsaving.invitations.serializers import InvitationSerializer
from foodsaving.pickups.models import PickupDate, PickupDateSeries, Feedback, pickup_done
from foodsaving.pickups.serializers import PickupDateSerializer, PickupDateSeriesSerializer, FeedbackSerializer
from foodsaving.stores.models import Store
from foodsaving.stores.serializers import StoreSerializer
from foodsaving.subscriptions import stats
from foodsaving.subscriptions.fcm import notify_subscribers
from foodsaving.subscriptions.models import ChannelSubscription, PushSubscription
from foodsaving.userauth.serializers import AuthUserSerializer
from foodsaving.users.serializers import UserSerializer
from foodsaving.utils import frontend_urls
from foodsaving.utils.frontend_urls import logo_url


@receiver(pre_save, sender=GroupMembership)
def user_became_editor(sender, instance, **kwargs):
    membership = instance
    if GROUP_EDITOR not in membership.roles:
        return

    if membership.id:
        old = GroupMembership.objects.get(id=membership.id)
        if GROUP_EDITOR in old.roles:
            return

    Bell.objects.create(
        type=BellType.USER_BECAME_EDITOR.value,
        user=membership.user,
    )


@receiver(post_save, sender=GroupApplication)
def new_applicant(sender, instance, **kwargs):
    application = instance

    for member in application.group.members.all():
        Bell.objects.create(
            type=BellType.NEW_APPLICANT.value,
            user=member,
        )


@receiver(pre_save, sender=GroupApplication)
def application_decided(sender, instance, **kwargs):
    application = instance

    if (application.status != GroupApplicationStatus.ACCEPTED.value
            and application.status != GroupApplicationStatus.DECLINED.value):
        return

    if application.id:
        old = GroupApplication.objects.get(id=application.id)
        if old.status == application.status:
            return

    bell_data = {
        'payload': {
            'decided_by': application.decided_by_id,
        },
    }

    if application.status == GroupApplicationStatus.ACCEPTED.value:
        bell_data['type'] = BellType.APPLICATION_ACCEPTED.value
    elif application.status == GroupApplicationStatus.DECLINED.value:
        bell_data['type'] = BellType.APPLICATION_DECLINED.value

    Bell.objects.create(user=application.user, **bell_data)

    for member in application.group.members.all():
        Bell.objects.create(user=member, **bell_data)


@receiver(pre_save, sender=PickupDate)
def feedback_possible(sender, instance, **kwargs):
    pickup = instance
    if not pickup.done_and_processed:
        return

    if pickup.id:
        old = PickupDate.objects.get(id=pickup.id)
        if old.done_and_processed == pickup.done_and_processed:
            return

    for collector in pickup.collectors.all():
        Bell.objects.create(
            user=collector, type=BellType.FEEDBACK_POSSIBLE.value, payload={
                'pickup': pickup.id,
            }
        )
