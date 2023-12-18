from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import IntegerField, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from pytz import utc

from karrot.activities.models import Activity, ActivityParticipant
from karrot.applications.models import Application, ApplicationStatus
from karrot.groups.models import GroupMembership, get_default_roles
from karrot.groups.roles import GROUP_EDITOR
from karrot.invitations.models import Invitation
from karrot.issues.models import Issue, OptionTypes, Voting
from karrot.notifications.models import Notification, NotificationMeta, NotificationType
from karrot.places.models import Place
from karrot.users.models import User


@receiver(pre_save, sender=GroupMembership)
def user_got_role(sender, instance, **kwargs):
    membership = instance
    if not membership.id:
        # membership was just created, skip notifications
        return

    if membership.roles == get_default_roles():
        return

    old = GroupMembership.objects.get(id=membership.id)
    new_roles = set(membership.roles).difference(old.roles)

    if len(new_roles) < 1:
        # skip if role was not changed
        return

    if GROUP_EDITOR in new_roles:
        Notification.objects.create(
            type=NotificationType.YOU_BECAME_EDITOR.value,
            user=membership.user,
            context={
                "group": membership.group.id,
            },
        )

        for member in membership.group.members.exclude(id=membership.user_id):
            Notification.objects.create(
                type=NotificationType.USER_BECAME_EDITOR.value,
                user=member,
                context={
                    "group": membership.group.id,
                    "user": membership.user.id,
                },
            )

    other_roles = new_roles.difference([GROUP_EDITOR])

    for role in other_roles:
        Notification.objects.create(
            type=NotificationType.YOU_GOT_ROLE.value,
            user=membership.user,
            context={
                "group": membership.group.id,
                "role": role,
            },
        )

        for member in membership.group.members.exclude(id=membership.user_id):
            Notification.objects.create(
                type=NotificationType.USER_GOT_ROLE.value,
                user=member,
                context={
                    "group": membership.group.id,
                    "user": membership.user.id,
                    "role": role,
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
                "group": application.group.id,
                "user": application.user.id,
                "application": application.id,
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
        "context": {
            "group": application.group.id,
            "application": application.id,
        },
    }

    if application.status == ApplicationStatus.ACCEPTED.value:
        notification_data["type"] = NotificationType.APPLICATION_ACCEPTED.value
    elif application.status == ApplicationStatus.DECLINED.value:
        notification_data["type"] = NotificationType.APPLICATION_DECLINED.value

    Notification.objects.create(user=application.user, **notification_data)


@receiver(pre_save, sender=Activity)
def feedback_possible(sender, instance, **kwargs):
    activity = instance
    if not activity.is_done:
        return

    if activity.id:
        # skip if activity was already processed
        old = Activity.objects.get(id=activity.id)
        if old.is_done == activity.is_done:
            return

        # skip if the activity does not take feedback
        if not activity.activity_type.has_feedback:
            return
    else:
        # Activity is not saved yet and can't have any participants
        return

    # TODO take into account that settings can change
    # better save feedback possible expiry in activity too
    expiry_date = activity.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    for user in activity.participants.all():
        Notification.objects.create(
            user=user,
            type=NotificationType.FEEDBACK_POSSIBLE.value,
            context={
                "group": activity.place.group.id,
                "activity": activity.id,
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
                "group": place.group.id,
                "place": place.id,
                "user": place.last_changed_by_id,
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
                "group": membership.group_id,
                "user": membership.user_id,
                "added_by": membership.added_by_id,
            },
        )


@receiver(post_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    """Remove notification when leaving group"""
    membership = instance

    types_to_keep = [
        NotificationType.CONFLICT_RESOLUTION_YOU_WERE_REMOVED.value,
    ]

    Notification.objects.filter(user=membership.user, context__group=membership.group_id).exclude(
        type__in=types_to_keep
    ).delete()


@receiver(pre_delete, sender=Invitation)
def invitation_accepted(sender, instance, **kwargs):
    invitation = instance

    # skip expired invitations
    if invitation.expires_at < timezone.now():
        return

    # search for the user who accepted the invitation, as we don't have access to the request object
    user = invitation.group.groupmembership_set.filter(added_by=invitation.invited_by).latest("created_at").user

    Notification.objects.create(
        user=invitation.invited_by,
        type=NotificationType.INVITATION_ACCEPTED.value,
        context={"group": invitation.group.id, "user": user.id},
    )


# Activities
@receiver(pre_delete, sender=ActivityParticipant)
def delete_activity_notifications_when_participant_leaves(sender, instance, **kwargs):
    participant = instance

    Notification.objects.order_by().not_expired().filter(
        Q(type=NotificationType.ACTIVITY_UPCOMING.value) | Q(type=NotificationType.ACTIVITY_DISABLED.value)
    ).filter(user=participant.user, context__activity_participant=participant.id).delete()


@receiver(pre_save, sender=Activity)
def activity_modified(sender, instance, **kwargs):
    activity = instance

    # abort if activity was just created
    if not activity.id:
        return

    old = Activity.objects.get(id=activity.id)

    participants = activity.activityparticipant_set

    def delete_notifications_for_participants(participants, type):
        Notification.objects.order_by().not_expired().filter(type=type).annotate(
            participant_id=Cast(KeyTextTransform("activity_participant", "context"), IntegerField())
        ).filter(participant_id__in=participants.values_list("id", flat=True)).delete()

    if old.is_disabled != activity.is_disabled:
        if activity.is_disabled:
            delete_notifications_for_participants(
                participants=participants,
                type=NotificationType.ACTIVITY_UPCOMING.value,
            )

            Notification.objects.create_for_activity_participants(
                participants=participants.exclude(user=activity.last_changed_by),
                type=NotificationType.ACTIVITY_DISABLED.value,
            )
        else:
            # activity is enabled
            Notification.objects.create_for_activity_participants(
                participants=participants.exclude(user=activity.last_changed_by),
                type=NotificationType.ACTIVITY_ENABLED.value,
            )
            # activity_upcoming notifications will automatically get created by cronjob

    if abs((old.date.start - activity.date.start).total_seconds()) > 60:
        Notification.objects.create_for_activity_participants(
            participants=participants.exclude(user=activity.last_changed_by),
            type=NotificationType.ACTIVITY_MOVED.value,
        )


# Issue
def create_notification_about_issue(issue, user, type):
    return Notification.objects.create(
        user=user,
        type=type,
        context={
            "issue": issue.id,
            "group": issue.group.id,
            "user": issue.affected_user.id,
        },
    )


@receiver(post_save, sender=Voting)
def conflict_resolution_issue_created_or_continued(sender, instance, created, **kwargs):
    if not created:
        return

    voting = instance
    issue = voting.issue

    # if there's only one voting, the issue has just been created
    if issue.votings.count() <= 1:
        for user in issue.group.members.exclude(id=issue.created_by_id).distinct():
            create_notification_about_issue(
                issue=issue,
                user=user,
                type=(
                    NotificationType.CONFLICT_RESOLUTION_CREATED.value
                    if user.id != issue.affected_user_id
                    else NotificationType.CONFLICT_RESOLUTION_CREATED_ABOUT_YOU.value
                ),
            )
    else:
        for user in issue.group.members.distinct():
            create_notification_about_issue(
                issue=issue,
                user=user,
                type=(
                    NotificationType.CONFLICT_RESOLUTION_CONTINUED.value
                    if user.id != issue.affected_user_id
                    else NotificationType.CONFLICT_RESOLUTION_CONTINUED_ABOUT_YOU.value
                ),
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

    for user in issue.group.members.distinct():
        create_notification_about_issue(
            issue=issue,
            user=user,
            type=(
                NotificationType.CONFLICT_RESOLUTION_DECIDED.value
                if user.id != issue.affected_user_id
                else NotificationType.CONFLICT_RESOLUTION_DECIDED_ABOUT_YOU.value
            ),
        )

    accepted_option = issue.latest_voting().accepted_option
    if accepted_option.type == OptionTypes.REMOVE_USER.value:
        Notification.objects.create(
            user=issue.affected_user,
            type=NotificationType.CONFLICT_RESOLUTION_YOU_WERE_REMOVED.value,
            context={
                "group": issue.group.id,
            },
        )


@receiver(post_save, sender=User)
def make_notification_meta(sender, instance, created, **kwargs):
    if not created:
        return

    user = instance
    # This is equivalent of not setting marked_at, by choosing a the earliest date possible
    # (but it has to be timezone-aware, otherwise there will be comparison errors)
    NotificationMeta.objects.get_or_create({"marked_at": datetime.min.replace(tzinfo=utc)}, user=user)
