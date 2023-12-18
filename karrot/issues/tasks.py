import sentry_sdk
from anymail.exceptions import AnymailAPIError
from django.contrib.auth import get_user_model
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from karrot.groups.models import GroupNotificationType, GroupMembership
from karrot.issues.emails import (
    prepare_new_conflict_resolution_email,
    prepare_conflict_resolution_continued_email,
    prepare_new_conflict_resolution_email_to_affected_user,
    prepare_conflict_resolution_continued_email_to_affected_user,
)
from karrot.issues.models import Voting, IssueStatus
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


@db_periodic_task(crontab(minute="*"))  # every minute
def process_expired_votings():
    with timer() as t:
        for voting in Voting.objects.filter(
            expires_at__lte=timezone.now(),
            accepted_option__isnull=True,
            issue__status=IssueStatus.ONGOING.value,
        ):
            # if nobody participated in the voting, cancel it!
            # otherwise it would result in a tie and continue forever
            if voting.participant_count() == 0:
                voting.issue.cancel()
                continue
            voting.calculate_results()

    stats_utils.periodic_task("issues__process_expired_votings", seconds=t.elapsed_seconds)


def get_users_to_notify(issue):
    return (
        issue.group.members.filter(
            groupmembership__in=GroupMembership.objects.active().with_notification_type(
                GroupNotificationType.CONFLICT_RESOLUTION
            ),
        )
        .exclude(
            groupmembership__user__in=get_user_model().objects.unverified(),
        )
        .distinct()
    )


def send_or_report_error(email):
    try:
        email.send()
    except AnymailAPIError:
        sentry_sdk.capture_exception()


@db_task()
def notify_about_new_conflict_resolution(issue):
    send_or_report_error(prepare_new_conflict_resolution_email_to_affected_user(issue))

    for user in get_users_to_notify(issue).exclude(id=issue.created_by_id).exclude(id=issue.affected_user_id):
        send_or_report_error(prepare_new_conflict_resolution_email(user, issue))


@db_task()
def notify_about_continued_conflict_resolution(issue):
    send_or_report_error(prepare_conflict_resolution_continued_email_to_affected_user(issue))

    for user in get_users_to_notify(issue).exclude(id=issue.affected_user_id):
        send_or_report_error(prepare_conflict_resolution_continued_email(user, issue))
