from dateutil.relativedelta import relativedelta
from django.db.models import Count, F
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from foodsaving.groups.models import Group
from foodsaving.pickups.emails import prepare_pickup_notification_email
from foodsaving.pickups.models import PickupDate


def fetch_group_pickups(group, start_date, end_date):
    return PickupDate.objects.annotate(
        num_collectors=Count('collectors')
    ).filter(
        store__group=group,
        date__gte=start_date,
        date__lt=end_date,
    ).order_by('date')


def fetch_user_pickups(group, user, start_date, end_date):
    pickups_filter = {
        'store__group': group,
        'date__gte': start_date,
        'date__lt': end_date,
    }

    return PickupDate.objects.filter(
        **pickups_filter,
        collectors__in=[user],
    ).order_by('date')


@db_periodic_task(crontab(minute=0))  # every hour
def daily_notifications():
    stats.periodic_task('pickups__daily_notifications')
    emails = []

    for group in Group.objects.all():
        with timezone.override(group.timezone):
            localnow = timezone.localtime()
            if localnow.hour == 19:

                midnight = localnow.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                ) + relativedelta(days=1)

                midnight_tomorrow = midnight + relativedelta(days=1)

                tonight_filter = {
                    'start_date': localnow,
                    'end_date': midnight,
                }

                tomorrow_filter = {
                    'start_date': midnight,
                    'end_date': midnight_tomorrow,
                }

                group_pickups_tonight_empty = fetch_group_pickups(group, **tonight_filter).filter(
                    num_collectors=0,
                )

                group_pickups_tonight_not_full = fetch_group_pickups(group, **tonight_filter).filter(
                    num_collectors__lt=F('max_collectors'),
                )

                group_pickups_tomorrow_empty = fetch_group_pickups(group, **tomorrow_filter).filter(
                    num_collectors=0,
                )

                group_pickups_tomorrow_not_full = fetch_group_pickups(group, **tomorrow_filter).filter(
                    num_collectors__lt=F('max_collectors'),
                )

                has_group_pickups = any([
                    pickups.count() > 0 for pickups in [
                        group_pickups_tonight_empty,
                        group_pickups_tonight_not_full,
                        group_pickups_tomorrow_empty,
                        group_pickups_tomorrow_not_full,
                    ]
                ])

                for user in group.members.all():
                    user_pickups_tonight = fetch_user_pickups(
                        **tonight_filter,
                        group=group,
                        user=user,
                    )

                    user_pickups_tomorrow = fetch_user_pickups(
                        **tomorrow_filter,
                        group=group,
                        user=user,
                    )

                    if has_group_pickups or any([
                        pickups.count() > 0 for pickups in [
                            user_pickups_tonight,
                            user_pickups_tomorrow,
                        ]
                    ]):
                        emails.append(prepare_pickup_notification_email(
                            user=user,
                            group=group,
                            tonight_date=localnow,
                            tomorrow_date=midnight,
                            user_pickups_tonight=user_pickups_tonight,
                            group_pickups_tonight_empty=group_pickups_tonight_empty,
                            group_pickups_tonight_not_full=group_pickups_tonight_not_full.exclude(
                                id__in=user_pickups_tonight,
                            ),
                            user_pickups_tomorrow=user_pickups_tomorrow,
                            group_pickups_tomorrow_empty=group_pickups_tomorrow_empty,
                            group_pickups_tomorrow_not_full=group_pickups_tomorrow_not_full.exclude(
                                id__in=user_pickups_tomorrow,
                            ),
                        ))

    print('would send {} emails', len(emails))

    for email in emails:
        # print(email.body)
        # print('\n\n\n\n\n')
        email.send()
