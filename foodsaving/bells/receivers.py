from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from foodsaving.applications.models import GroupApplication, GroupApplicationStatus
from foodsaving.bells.models import Bell, BellType
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.models import PickupDate
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

    for member in membership.group.members.all():
        Bell.objects.create(
            type=BellType.USER_BECAME_EDITOR.value,
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
        Bell.objects.create(
            type=BellType.NEW_APPLICANT.value,
            user=member,
            context={
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

    # clean up new_application bells for this application
    Bell.objects.filter(
        type=BellType.NEW_APPLICANT.value,
        context__application=application.id,
    ).delete()

    # do not create more bells if application was withdrawn
    if application.status == GroupApplicationStatus.WITHDRAWN.value:
        return

    bell_data = {
        'context': {
            'application': application.id,
        },
    }

    if application.status == GroupApplicationStatus.ACCEPTED.value:
        bell_data['type'] = BellType.APPLICATION_ACCEPTED.value
    elif application.status == GroupApplicationStatus.DECLINED.value:
        bell_data['type'] = BellType.APPLICATION_DECLINED.value

    Bell.objects.create(user=application.user, **bell_data)


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

    # TODO take into account that settings can change
    # better save feedback possible expiry in pickup too
    expiry_date = pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    for collector in pickup.collectors.all():
        Bell.objects.create(
            user=collector,
            type=BellType.FEEDBACK_POSSIBLE.value,
            context={
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
        Bell.objects.create(
            user=member,
            type=BellType.NEW_STORE.value,
            context={
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
        Bell.objects.create(
            user=member,
            type=BellType.NEW_MEMBER.value,
            context={
                'group': membership.group.id,
                'user': membership.added_by_id,
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

    Bell.objects.create(
        user=invitation.invited_by,
        type=BellType.INVITATION_ACCEPTED.value,
        context={
            'group': invitation.group.id,
            'user': user.id
        }
    )
