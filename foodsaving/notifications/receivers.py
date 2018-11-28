from dateutil.relativedelta import relativedelta
from django.conf import settings
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
    if not pickup.done_and_processed:
        return

    if pickup.id:
        # skip if pickup was already processed
        old = PickupDate.objects.get(id=pickup.id)
        if old.done_and_processed == pickup.done_and_processed:
            return
    else:
        # Pickup is not saved yet and can't have any collectors
        return

    # TODO take into account that settings can change
    # better save feedback possible expiry in pickup too
    expiry_date = pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    for collector in pickup.collectors.all():
        Notification.objects.create(
            user=collector,
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

    for member in store.group.members.exclude(id=store.created_by_id):
        Notification.objects.create(
            user=member,
            type=NotificationType.NEW_STORE.value,
            context={
                'group': store.group.id,
                'store': store.id,
                'user': store.created_by_id,
            },
        )


@receiver(post_save, sender=GroupMembership)
def new_member(sender, instance, created, **kwargs):
    if not created:
        return

    membership = instance

    for member in membership.group.members.exclude(id__in=(membership.user_id, membership.added_by_id)):
        Notification.objects.create(
            user=member,
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
def pickup_collector_removed(sender, instance, **kwargs):
    collector = instance

    Notification.objects.not_expired().filter(
        type=NotificationType.PICKUP_UPCOMING.value,
        user=collector.user,
        context__pickup_collector=collector.id,
    ).delete()
