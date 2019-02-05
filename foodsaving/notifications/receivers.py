from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import IntegerField, Q
from django.db.models.functions import Cast
from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from foodsaving.applications.models import Application, ApplicationStatus
from foodsaving.issues.models import Issue, Voting, OptionTypes
from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.models import PickupDate, PickupDateCollector
from foodsaving.places.models import Place


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

    if membership.group.is_playground():
        return

    for member in membership.group.members.exclude(id=membership.user_id):
        Notification.objects.create(
            type=NotificationType.USER_BECAME_EDITOR.value,
            user=member,
            context={
                'group': membership.group.id,
                'user': membership.user.id,
            },
        )


@receiver(post_save, sender=Application)
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


@receiver(pre_save, sender=Application)
def application_decided(sender, instance, **kwargs):
    application = instance

    if application.status not in (
            ApplicationStatus.ACCEPTED.value,
            ApplicationStatus.DECLINED.value,
            ApplicationStatus.WITHDRAWN.value,
    ):
        return

    if application.id:
        # skip if status was not changed
        old = Application.objects.get(id=application.id)
        if old.status == application.status:
            return

    # clean up new_application notifications for this application
    Notification.objects.filter(
        type=NotificationType.NEW_APPLICANT.value,
        context__application=application.id,
    ).delete()

    # do not create more notifications if application was withdrawn
    if application.status == ApplicationStatus.WITHDRAWN.value:
        return

    notification_data = {
        'context': {
            'group': application.group.id,
            'application': application.id,
        },
    }

    if application.status == ApplicationStatus.ACCEPTED.value:
        notification_data['type'] = NotificationType.APPLICATION_ACCEPTED.value
    elif application.status == ApplicationStatus.DECLINED.value:
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
    expiry_date = pickup.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    for user in pickup.collectors.all():
        Notification.objects.create(
            user=user,
            type=NotificationType.FEEDBACK_POSSIBLE.value,
            context={
                'group': pickup.place.group.id,
                'pickup': pickup.id,
            },
            expires_at=expiry_date,
        )


@receiver(post_save, sender=Place)
def new_place(sender, instance, created, **kwargs):
    if not created:
        return

    place = instance

    for user in place.group.members.exclude(id=place.last_changed_by_id):
        Notification.objects.create(
            user=user,
            type=NotificationType.NEW_PLACE.value,
            context={
                'group': place.group.id,
                'place': place.id,
                'user': place.last_changed_by_id,
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


# Pickups
@receiver(pre_delete, sender=PickupDateCollector)
def delete_pickup_notifications_when_collector_leaves(sender, instance, **kwargs):
    collector = instance

    Notification.objects.order_by().not_expired()\
        .filter(Q(type=NotificationType.PICKUP_UPCOMING.value) | Q(type=NotificationType.PICKUP_DISABLED.value))\
        .filter(user=collector.user, context__pickup_collector=collector.id)\
        .delete()


@receiver(pre_save, sender=PickupDate)
def pickup_modified(sender, instance, **kwargs):
    pickup = instance

    # abort if pickup was just created
    if not pickup.id:
        return

    old = PickupDate.objects.get(id=pickup.id)

    collectors = pickup.pickupdatecollector_set

    def delete_notifications_for_collectors(collectors, type):
        Notification.objects.order_by().not_expired() \
            .filter(type=type) \
            .annotate(collector_id=Cast(KeyTextTransform('pickup_collector', 'context'), IntegerField())) \
            .filter(collector_id__in=collectors.values_list('id', flat=True)) \
            .delete()

    if old.is_disabled != pickup.is_disabled:
        if pickup.is_disabled:
            delete_notifications_for_collectors(
                collectors=collectors,
                type=NotificationType.PICKUP_UPCOMING.value,
            )

            Notification.objects.create_for_pickup_collectors(
                collectors=collectors.exclude(user=pickup.last_changed_by),
                type=NotificationType.PICKUP_DISABLED.value,
            )
        else:
            # pickup is enabled
            Notification.objects.create_for_pickup_collectors(
                collectors=collectors.exclude(user=pickup.last_changed_by),
                type=NotificationType.PICKUP_ENABLED.value,
            )
            # pickup_upcoming notifications will automatically get created by cronjob

    if abs((old.date.start - pickup.date.start).total_seconds()) > 60:
        Notification.objects.create_for_pickup_collectors(
            collectors=collectors.exclude(user=pickup.last_changed_by),
            type=NotificationType.PICKUP_MOVED.value,
        )


# Issue
def create_notification_about_issue(issue, user, type):
    return Notification.objects.create(
        user=user,
        type=type,
        context={
            'issue': issue.id,
            'group': issue.group.id,
            'affected_user': issue.affected_user.id,
        }
    )


@receiver(post_save, sender=Voting)
def conflict_resolution_issue_created_or_continued(sender, instance, created, **kwargs):
    if not created:
        return

    voting = instance
    issue = voting.issue

    # if there's only one voting, the issue has just been created
    if issue.votings.count() <= 1:
        for user in issue.participants.exclude(id=issue.created_by_id).distinct():
            create_notification_about_issue(
                issue=issue,
                user=user,
                type=(
                    NotificationType.CONFLICT_RESOLUTION_CREATED.value if user.id != issue.affected_user_id else
                    NotificationType.CONFLICT_RESOLUTION_CREATED_ABOUT_YOU.value
                )
            )
    else:
        for user in issue.participants.distinct():
            create_notification_about_issue(
                issue=issue,
                user=user,
                type=(
                    NotificationType.CONFLICT_RESOLUTION_CONTINUED.value if user.id != issue.affected_user_id else
                    NotificationType.CONFLICT_RESOLUTION_CONTINUED_ABOUT_YOU.value
                )
            )


@receiver(pre_save, sender=Issue)
def conflict_resolution_issue_decided(sender, instance, **kwargs):
    issue = instance

    # abort if just created
    if not issue.id:
        return

    # abort if issue is not decided or was already decided
    old = Issue.objects.get(id=issue.id)
    if old.is_decided() or not issue.is_decided():
        return

    for user in issue.participants.distinct():
        create_notification_about_issue(
            issue=issue,
            user=user,
            type=(
                NotificationType.CONFLICT_RESOLUTION_DECIDED.value
                if user.id != issue.affected_user_id else NotificationType.CONFLICT_RESOLUTION_DECIDED_ABOUT_YOU.value
            )
        )

    accepted_option = issue.latest_voting().accepted_option
    if accepted_option.type == OptionTypes.REMOVE_USER.value:
        Notification.objects.create(
            user=issue.affected_user,
            type=NotificationType.CONFLICT_RESOLUTION_YOU_WERE_REMOVED.value,
            context={
                'group': issue.group.id,
            }
        )
