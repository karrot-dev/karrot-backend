from anymail.exceptions import AnymailAPIError
from django.contrib.auth import get_user_model
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.cases.emails import prepare_new_conflict_resolution_email, \
    prepare_conflict_resolution_case_continued_email
from foodsaving.cases.models import Voting
from foodsaving.groups.models import GroupNotificationType


@db_periodic_task(crontab(minute='*'))  # every minute
def process_expired_votings():
    for voting in Voting.objects.filter(expires_at__lte=timezone.now(), accepted_option__isnull=True):
        voting.calculate_results()


def get_users_to_notify(case):
    return case.user_queryset().filter(
        groupmembership__roles__contains=[GroupNotificationType.CONFLICT_RESOLUTION],
        groupmembership__inactive_at__isnull=True,
    ).exclude(id__in=get_user_model().objects.unverified_or_ignored())


@db_task()
def notify_about_new_conflict_resolution_case(case):
    for user in get_users_to_notify(case):
        try:
            prepare_new_conflict_resolution_email(user, case).send()
        except AnymailAPIError:
            sentry_client.captureException()


@db_task()
def notify_about_continued_conflict_resolution_case(case):
    for user in get_users_to_notify(case):
        try:
            prepare_conflict_resolution_case_continued_email(user, case).send()
        except AnymailAPIError:
            sentry_client.captureException()
