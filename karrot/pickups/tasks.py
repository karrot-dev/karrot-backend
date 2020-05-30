from dateutil.relativedelta import relativedelta
from django.db.models import F, QuerySet
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from karrot.groups.models import Group, GroupMembership, GroupNotificationType
from karrot.pickups import stats
from karrot.pickups.emails import prepare_pickup_notification_email
from karrot.pickups.models import PickupDate, PickupDateSeries
from karrot.places.models import PlaceStatus
from karrot.users.models import User
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


@db_periodic_task(crontab(minute='*'))  # every minute
def process_finished_pickup_dates():
    with timer() as t:
        PickupDate.objects.process_finished_pickup_dates()
    stats_utils.periodic_task('pickups__process_finished_pickup_dates', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute=0))  # every hour
def update_pickups():
    with timer() as t:
        PickupDateSeries.objects.update_pickups()
    stats_utils.periodic_task('pickups__update_pickups', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute=0))  # we check every hour
def daily_pickup_notifications():

    with timer() as t:
        for group in Group.objects.all():
            with timezone.override(group.timezone):
                if timezone.localtime().hour != 20:  # only at 8pm local time
                    continue

                for data in fetch_pickup_notification_data_for_group(group):
                    prepare_pickup_notification_email(**data).send()
                    stats.pickup_notification_email(
                        group=data['group'], **{k: v.count()
                                                for k, v in data.items() if isinstance(v, QuerySet)}
                    )

    stats_utils.periodic_task('pickups__daily_pickup_notifications', seconds=t.elapsed_seconds)


def fetch_pickup_notification_data_for_group(group):
    results = []
    localnow = timezone.localtime()

    midnight = localnow.replace(hour=0, minute=0, second=0, microsecond=0) + relativedelta(days=1)
    midnight_tomorrow = midnight + relativedelta(days=1)

    tonight = {'date__startswith__gte': localnow, 'date__startswith__lt': midnight}
    tomorrow = {'date__startswith__gte': midnight, 'date__startswith__lt': midnight_tomorrow}

    empty = {'num_collectors': 0}
    not_full = {'num_collectors__gt': 0, 'num_collectors__lt': F('max_collectors')}

    pickups = PickupDate.objects.exclude_disabled().annotate_num_collectors().filter(
        place__status=PlaceStatus.ACTIVE.value,
        place__group=group,
    ).order_by('date')

    users = group.members.filter(
        groupmembership__in=GroupMembership.objects.active().with_notification_type(
            GroupNotificationType.DAILY_PICKUP_NOTIFICATION
        ),
    ).exclude(
        groupmembership__user__in=User.objects.unverified(),
    )

    for user in users:
        subscribed_places_pickups = pickups.filter(place__placesubscription__user=user)

        tonight_empty = subscribed_places_pickups.filter(**tonight, **empty)
        tomorrow_empty = subscribed_places_pickups.filter(**tomorrow, **empty)
        base_tonight_not_full = subscribed_places_pickups.filter(**tonight, **not_full)
        base_tomorrow_not_full = subscribed_places_pickups.filter(**tomorrow, **not_full)

        has_empty_pickups = any(v.count() > 0 for v in [tonight_empty, tomorrow_empty])

        user_pickups = PickupDate.objects.filter(
            place__group=group,
            collectors__in=[user],
        ).order_by('date')

        tonight_user = user_pickups.filter(**tonight)
        tomorrow_user = user_pickups.filter(**tomorrow)

        tonight_not_full = base_tonight_not_full.exclude(collectors__in=[user])
        tomorrow_not_full = base_tomorrow_not_full.exclude(collectors__in=[user])

        has_user_pickups = any([
            v.count() > 0 for v in [
                tonight_user,
                tomorrow_user,
                tonight_not_full,
                tomorrow_not_full,
            ]
        ])

        if has_empty_pickups or has_user_pickups:
            results.append({
                'user': user,
                'group': group,
                'tonight_date': localnow,
                'tomorrow_date': midnight,
                'tonight_user': tonight_user,
                'tonight_empty': tonight_empty,
                'tonight_not_full': tonight_not_full,
                'tomorrow_user': tomorrow_user,
                'tomorrow_empty': tomorrow_empty,
                'tomorrow_not_full': tomorrow_not_full,
            })

    return results
