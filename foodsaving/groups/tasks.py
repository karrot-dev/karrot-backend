from anymail.exceptions import AnymailAPIError
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task
from influxdb_metrics.loader import write_points
from raven.contrib.django.raven_compat.models import client as sentry_client

from config import settings
from foodsaving.applications.stats import get_group_application_stats
from foodsaving.groups.emails import (
    prepare_user_inactive_in_group_email, prepare_group_summary_data, calculate_group_summary_dates,
    prepare_group_summary_emails, prepare_user_removal_from_group_email
)
from foodsaving.groups.models import Group, GroupStatus
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.stats import get_group_members_stats, get_group_stores_stats, group_summary_email
from foodsaving.utils import stats_utils


@db_periodic_task(crontab(minute=0))  # every hour
def record_group_stats():
    stats_utils.periodic_task('group__record_group_stats')

    points = []

    for group in Group.objects.all():
        points.extend(get_group_members_stats(group))
        points.extend(get_group_stores_stats(group))
        points.extend(get_group_application_stats(group))

    write_points(points)


@db_periodic_task(crontab(hour=2, minute=0))  # 2am every day
def process_inactive_users():
    now = timezone.now()

    count_users_flagged_inactive = 0
    count_users_flagged_for_removal = 0
    count_users_removed = 0

    # first, we mark them as inactive

    inactive_threshold_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP)
    for membership in GroupMembership.objects.filter(
            lastseen_at__lte=inactive_threshold_date,
            inactive_at=None,
    ):
        # only send emails if group itself is marked as active
        if membership.group.status == GroupStatus.ACTIVE.value:
            prepare_user_inactive_in_group_email(membership.user, membership.group).send()
        membership.inactive_at = now
        membership.save()
        count_users_flagged_inactive += 1

    # then, if they have been inactive for some time, we warn them we will remove them

    removal_notification_date = now - relativedelta(
        months=settings.NUMBER_OF_INACTIVE_MONTHS_UNTIL_REMOVAL_FROM_GROUP_NOTIFICATION
    )
    for membership in GroupMembership.objects.filter(removal_notification_at=None,
                                                     inactive_at__lte=removal_notification_date):
        if membership.group.status == GroupStatus.ACTIVE.value:
            prepare_user_removal_from_group_email(membership.user, membership.group).send()
        membership.removal_notification_at = now
        membership.save()
        count_users_flagged_for_removal += 1

    # and finally, actually remove them

    removal_date = now - timedelta(days=settings.NUMBER_OF_DAYS_AFTER_REMOVAL_NOTIFICATION_WE_ACTUALLY_REMOVE_THEM)
    for membership in GroupMembership.objects.filter(removal_notification_at__lte=removal_date):
        membership.delete()
        count_users_removed += 1

    stats_utils.periodic_task(
        'group__process_inactive_users', {
            'count_users_flagged_inactive': count_users_flagged_inactive,
            'count_users_flagged_for_removal': count_users_flagged_for_removal,
            'count_users_removed': count_users_removed,
        }
    )


@db_periodic_task(crontab(day_of_week=0, hour=8, minute=0))  # send 8am every Sunday
def send_summary_emails():
    email_count = 0
    recipient_count = 0

    groups = Group.objects.annotate(member_count=Count('members')).filter(member_count__gt=0)

    for group in groups:

        from_date, to_date = calculate_group_summary_dates(group)

        if not group.sent_summary_up_to or group.sent_summary_up_to < to_date:

            email_recipient_count = 0

            context = prepare_group_summary_data(group, from_date, to_date)
            if context['has_activity']:
                for email in prepare_group_summary_emails(group, context):
                    try:
                        email.send()
                        email_count += 1
                        email_recipient_count += len(email.to)
                    except AnymailAPIError:
                        sentry_client.captureException()

            # we save this even if some of the email sending fails, no retries right now basically...
            # we also save if no emails were sent due to missing activity, to not try again over and over.
            group.sent_summary_up_to = to_date
            group.save()

            group_summary_email(
                group,
                email_recipient_count=email_recipient_count,
                feedback_count=context['feedbacks'].count(),
                message_count=context['messages'].count(),
                new_user_count=context['new_users'].count(),
                pickups_done_count=context['pickups_done_count'],
                pickups_missed_count=context['pickups_missed_count'],
                has_activity=context['has_activity'],
            )

            recipient_count += email_recipient_count

    stats_utils.periodic_task(
        'group__send_summary_emails', {
            'recipient_count': recipient_count,
            'email_count': email_count,
        }
    )


@db_periodic_task(crontab(hour=3, minute=3))  # 3 am every day
def mark_inactive_groups():
    for group in Group.objects.filter(status=GroupStatus.ACTIVE.value):
        if not group.has_recent_activity():
            group.status = GroupStatus.INACTIVE.value
            group.save()
