from huey import crontab
from huey.contrib.djhuey import db_periodic_task
from influxdb_metrics.loader import write_points

from foodsaving.groups import stats
from foodsaving.groups.models import Group

from django.utils import timezone
from foodsaving.groups.models import GroupMembership
from config import settings
from foodsaving.utils.email_utils import prepare_user_inactive_in_group_email, prepare_user_removed_from_group_email

from datetime import datetime, timedelta


@db_periodic_task(crontab(hour='*'))
def record_stats():
    points = []

    for group in Group.objects.all():
        points.extend(stats.get_group_members_stats(group))
        points.extend(stats.get_group_stores_stats(group))

    write_points(points)


def send_inactive_in_group_notification_to_user(user, group):
    email = prepare_user_inactive_in_group_email(user, group)
    email.send()


def send_removal_from_group_notification_to_user(user, group):
    email = prepare_user_removed_from_group_email(user, group)
    email.send()


@db_periodic_task(crontab(hour='2', minute='0'))
def process_inactive_users():
    now = timezone.now()

    count_users_flagged_inactive = 0
    count_users_removed = 0

    remove_threshold_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_REMOVED_FROM_GROUP)
    for gm in GroupMembership.objects.all().filter(lastseen_at__lte=remove_threshold_date, active=False):
        send_removal_from_group_notification_to_user(gm.user, gm.group)
        gm.delete()
        count_users_removed += 1

    inactive_threshold_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP)
    for gm in GroupMembership.objects.all().filter(lastseen_at__lte=inactive_threshold_date, active=True):
        send_inactive_in_group_notification_to_user(gm.user, gm.group)
        gm.active = False
        gm.save()
        count_users_flagged_inactive += 1

