from anymail.exceptions import AnymailAPIError
from django.contrib.auth import get_user_model
from huey.contrib.djhuey import db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from foodsaving.applications.emails import prepare_new_application_notification_email, \
    prepare_application_accepted_email, prepare_application_declined_email
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.models import GroupNotificationType


@db_task()
def notify_members_about_new_application(application):
    users = application.group.members.filter(
        groupmembership__in=GroupMembership.objects.active().with_notification_type(
            GroupNotificationType.NEW_APPLICATION
        ),
    ).exclude(
        groupmembership__user__in=get_user_model().objects.unverified_or_ignored(),
    )

    for user in users:
        try:
            prepare_new_application_notification_email(user, application).send()
        except AnymailAPIError:
            sentry_client.captureException()


@db_task()
def notify_about_accepted_application(application):
    prepare_application_accepted_email(application).send()


@db_task()
def notify_about_declined_application(application):
    prepare_application_declined_email(application).send()
