from anymail.exceptions import AnymailAPIError
from django.contrib.auth import get_user_model
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.issues.emails import prepare_new_conflict_resolution_email, \
    prepare_conflict_resolution_continued_email, prepare_new_conflict_resolution_email_to_affected_user, \
    prepare_conflict_resolution_continued_email_to_affected_user
from foodsaving.issues.models import Voting, IssueStatus
from foodsaving.groups.models import GroupNotificationType


@db_periodic_task(crontab(minute='*'))  # every minute
def process_expired_votings():
    for voting in Voting.objects.filter(
            expires_at__lte=timezone.now(),
            accepted_option__isnull=True,
            issue__status=IssueStatus.ONGOING.value,
    ):
        voting.calculate_results()


def get_users_to_notify(issue):
    return issue.participants.filter(
        groupmembership__notification_types__contains=[GroupNotificationType.CONFLICT_RESOLUTION],
        groupmembership__inactive_at__isnull=True,
    ).exclude(id__in=get_user_model().objects.unverified_or_ignored()).distinct()


@db_task()
def notify_about_new_conflict_resolution(issue):
    for user in get_users_to_notify(issue).exclude(id=issue.created_by_id):
        try:
            if user.id == issue.affected_user_id:
                prepare_new_conflict_resolution_email_to_affected_user(issue).send()
            else:
                prepare_new_conflict_resolution_email(user, issue).send()
        except AnymailAPIError:
            sentry_client.captureException()


@db_task()
def notify_about_continued_conflict_resolution(issue):
    for user in get_users_to_notify(issue):
        try:
            if user.id == issue.affected_user_id:
                prepare_conflict_resolution_continued_email_to_affected_user(issue).send()
            else:
                prepare_conflict_resolution_continued_email(user, issue).send()
        except AnymailAPIError:
            sentry_client.captureException()
