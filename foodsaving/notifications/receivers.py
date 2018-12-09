from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import IntegerField, Q
from django.db.models.functions import Cast
from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from foodsaving.applications.models import GroupApplication, GroupApplicationStatus
from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.models import PickupDate, PickupDateCollector
from foodsaving.stores.models import Store


@receiver(pre_save, sender=GroupMembership)
def user_became_editor(sender, instance, **kwargs):
    membership = instance
    if GROUP_EDITOR not in membership.roles:
        return

    if membership.id:
        # skip if role was not changed
        old = GroupMembership.objects.get(id=membership.id)
        if GROUP_EDITOR in old.roles:
            return

    Notification.objects.create(
        type=NotificationType.YOU_BECAME_EDITOR.value,
        user=membership.user,
        context={
            'group': membership.group.id,
        },
    )

    for member in membership.group.members.exclude(id=membership.user_id):
        Notification.objects.create(
            type=NotificationType.USER_BECAME_EDITOR.value,
            user=member,
            context={
                'group': membership.group.id,
                'user': membership.user.id,
            },
        )


@receiver(post_save, sender=GroupApplication)
def new_applicant(sender, instance, created, **kwargs):
    if not created:
        return

    application = instance

    for member in application.group.members.all():
        Notification.objects.create(
            type=NotificationType.NEW_APPLICANT.value,
            user=member,
            context={
                'group': application.group.id,
                'user': application.user.id,
                'application': application.id,
            },
        )


@receiver(pre_save, sender=GroupApplication)
def application_decided(sender, instance, **kwargs):
    application = instance

    if application.status not in (
            GroupApplicationStatus.ACCEPTED.value,
            GroupApplicationStatus.DECLINED.value,
            GroupApplicationStatus.WITHDRAWN.value,
    ):
        return

    if application.id:
        # skip if status was not changed
        old = GroupApplication.objects.get(id=application.id)
        if old.status == application.status:
            return

    # clean up new_application notifications for this application
    Notification.objects.filter(
        type=NotificationType.NEW_APPLICANT.value,
        context__application=application.id,
    ).delete()

    # do not create more notifications if application was withdrawn
    if application.status == GroupApplicationStatus.WITHDRAWN.value:
        return

    notification_data = {
        'context': {
            'group': application.group.id,
            'application': application.id,
        },
    }

    if application.status == GroupApplicationStatus.ACCEPTED.value:
        notification_data['type'] = NotificationType.APPLICATION_ACCEPTED.value
    elif application.status == GroupApplicationStatus.DECLINED.value:
        notification_data['type'] = NotificationType.APPLICATION_DECLINED.value

    Notification.objects.create(user=application.user, **notification_data)


@receiver(pre_save, sender=PickupDate)
def feedback_possible(sender, instance, **kwargs):
    pickup = instance
    if not pickup.feedback_possible:
        return

    if pickup.id:
        # skip if pickup was already processed
        old = PickupDate.objects.get(id=pickup.id)
        if old.feedback_possible == pickup.feedback_possible:
            return
    else:
        # Pickup is not saved yet and can't have any collectors
        return

    # TODO take into account that settings can change
    # better save feedback possible expiry in pickup too
    expiry_date = pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    for user in pickup.collectors.all():
        Notification.objects.create(
            user=user,
            type=NotificationType.FEEDBACK_POSSIBLE.value,
            context={
                'group': pickup.store.group.id,
                'pickup': pickup.id,
            },
            expires_at=expiry_date,
        )


@receiver(post_save, sender=Store)
def new_store(sender, instance, created, **kwargs):
    if not created:
        return

    store = instance

    for user in store.group.members.exclude(id=store.last_changed_by_id):
        Notification.objects.create(
            user=user,
            type=NotificationType.NEW_STORE.value,
            context={
                'group': store.group.id,
                'store': store.id,
                'user': store.last_changed_by_id,
            },
        )


@receiver(post_save, sender=GroupMembership)
def new_member(sender, instance, created, **kwargs):
    if not created:
        return

    membership = instance

    for user in membership.group.members.exclude(id__in=(membership.user_id, membership.added_by_id)):
        Notification.objects.create(
            user=user,
            type=NotificationType.NEW_MEMBER.value,
            context={
                'group': membership.group_id,
                'user': membership.user_id,
                'added_by': membership.added_by_id,
            },
        )


@receiver(pre_delete, sender=Invitation)
def invitation_accepted(sender, instance, **kwargs):
    invitation = instance

    # skip expired invitations
    if invitation.expires_at < timezone.now():
        return

    # search for the user who accepted the invitation, as we don't have access to the request object
    user = invitation.group.groupmembership_set.filter(added_by=invitation.invited_by).latest('created_at').user

    Notification.objects.create(
        user=invitation.invited_by,
        type=NotificationType.INVITATION_ACCEPTED.value,
        context={
            'group': invitation.group.id,
            'user': user.id
        }
    )


@receiver(pre_delete, sender=PickupDateCollector)
def delete_pickup_notifications_when_collector_leaves(sender, instance, **kwargs):
    collector = instance

    Notification.objects.order_by().not_expired()\
        .filter(Q(type=NotificationType.PICKUP_UPCOMING.value) | Q(type=NotificationType.PICKUP_CANCELLED.value))\
        .filter(user=collector.user, context__pickup_collector=collector.id)\
        .delete()


@receiver(pre_save, sender=PickupDate)
def pickup_cancelled_or_uncancelled(sender, instance, **kwargs):
    pickup = instance

    # abort pickup was just created
    if not pickup.id:
        return

    # abort if pickup cancel status didn't change
    old = PickupDate.objects.get(id=pickup.id)
    if old.is_cancelled == pickup.is_cancelled:
        return

    collectors = pickup.pickupdatecollector_set

    def delete_notifications_by_type_and_collectors(type, collectors):
        Notification.objects.order_by().not_expired() \
            .filter(type=type) \
            .annotate(collector_id=Cast(KeyTextTransform('pickup_collector', 'context'), IntegerField())) \
            .filter(collector_id__in=collectors.values_list('id', flat=True)) \
            .delete()

    if pickup.is_cancelled:
        delete_notifications_by_type_and_collectors(type=NotificationType.PICKUP_UPCOMING.value, collectors=collectors)

        # create pickup_cancelled notifications
        for collector in collectors.exclude(user=pickup.last_changed_by):
            Notification.objects.create(
                user=collector.user,
                type=NotificationType.PICKUP_CANCELLED.value,
                context={
                    'group': pickup.group.id,
                    'store': pickup.store.id,
                    'pickup': pickup.id,
                    'pickup_collector': collector.id,
                }
            )
    else:
        # pickup is uncancelled
        delete_notifications_by_type_and_collectors(
            type=NotificationType.PICKUP_CANCELLED.value, collectors=collectors
        )
        # pickup_upcoming notifications will automatically get created by cronjob
