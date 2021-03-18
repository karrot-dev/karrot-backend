from babel.dates import format_time, format_datetime
from dateutil.relativedelta import relativedelta
from django.db.models import F, QuerySet
from django.utils import timezone, translation
from django.utils.text import Truncator
from django.utils.translation import gettext as _
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from karrot.activities import stats
from karrot.activities.emails import prepare_activity_notification_email
from karrot.activities.models import Activity, ActivitySeries, ActivityParticipant
from karrot.groups.models import Group, GroupMembership, GroupNotificationType
from karrot.places.models import PlaceStatusOld
from karrot.subscriptions.models import PushSubscription
from karrot.subscriptions.tasks import notify_subscribers_by_device
from karrot.users.models import User
from karrot.utils import stats_utils, frontend_urls
from karrot.utils.stats_utils import timer


def is_today(dt):
    return dt.date() == timezone.now().date()


def is_past(dt):
    return dt < timezone.now()


@db_task()
def activity_reminder(participant_id):
    participant = ActivityParticipant.objects.filter(id=participant_id).first()
    if not participant:
        return

    activity = participant.activity
    user = participant.user
    language = user.language
    tz = activity.group.timezone

    with translation.override(language), timezone.override(tz):
        if is_past(activity.date.start):
            return

        subscriptions = PushSubscription.objects.filter(user=user)
        if subscriptions.count() == 0:
            return

        emoji = '⏰'

        if is_today(activity.date.start):
            when = format_time(
                activity.date.start,
                format='short',
                locale=translation.to_locale(language),
                tzinfo=tz,
            )
        else:
            when = format_datetime(
                activity.date.start,
                format='medium',  # short gives US date format in English, is confusing!
                locale=translation.to_locale(language),
                tzinfo=tz,
            )

        where = ', '.join(part for part in [activity.place.name, activity.place.address] if part)

        title = _('Upcoming %(activity_type)s') % {'activity_type': activity.activity_type.get_translated_name()}
        title = f'{emoji} {title}!'

        body = Truncator(' / '.join(part for part in [when, where, activity.description] if part)).chars(num=1000)

        click_action = frontend_urls.activity_detail_url(activity)

        notify_subscribers_by_device(
            subscriptions,
            click_action=click_action,
            fcm_options={
                'message_title': title,
                'message_body': body,
                'tag': 'activity:{}'.format(activity.id),
            }
        )


@db_periodic_task(crontab(minute='*'))  # every minute
def process_finished_activities():
    with timer() as t:
        Activity.objects.process_finished_activities()
    stats_utils.periodic_task('activities__process_finished_activities', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute=0))  # every hour
def update_activities():
    with timer() as t:
        ActivitySeries.objects.update_activities()
    stats_utils.periodic_task('activities__update_activities', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute=0))  # we check every hour
def daily_activity_notifications():

    with timer() as t:
        for group in Group.objects.all():
            with timezone.override(group.timezone):
                if timezone.localtime().hour != 20:  # only at 8pm local time
                    continue

                for data in fetch_activity_notification_data_for_group(group):
                    prepare_activity_notification_email(**data).send()
                    stats.activity_notification_email(
                        group=data['group'], **{k: v.count()
                                                for k, v in data.items() if isinstance(v, QuerySet)}
                    )

    stats_utils.periodic_task('activities__daily_activity_notifications', seconds=t.elapsed_seconds)


def fetch_activity_notification_data_for_group(group):
    results = []
    localnow = timezone.localtime()

    midnight = localnow.replace(hour=0, minute=0, second=0, microsecond=0) + relativedelta(days=1)
    midnight_tomorrow = midnight + relativedelta(days=1)

    tonight = {'date__startswith__gte': localnow, 'date__startswith__lt': midnight}
    tomorrow = {'date__startswith__gte': midnight, 'date__startswith__lt': midnight_tomorrow}

    empty = {'num_participants': 0}
    not_full = {'num_participants__gt': 0, 'num_participants__lt': F('max_participants')}

    activities = Activity.objects.exclude_disabled().annotate_num_participants().filter(
        place__status=PlaceStatusOld.ACTIVE.value,
        place__group=group,
    ).order_by('date')

    users = group.members.filter(
        groupmembership__in=GroupMembership.objects.active().with_notification_type(
            GroupNotificationType.DAILY_ACTIVITY_NOTIFICATION
        ),
    ).exclude(
        groupmembership__user__in=User.objects.unverified(),
    )

    for user in users:
        subscribed_places_activities = activities.filter(place__placesubscription__user=user)

        tonight_empty = subscribed_places_activities.filter(**tonight, **empty)
        tomorrow_empty = subscribed_places_activities.filter(**tomorrow, **empty)
        base_tonight_not_full = subscribed_places_activities.filter(**tonight, **not_full)
        base_tomorrow_not_full = subscribed_places_activities.filter(**tomorrow, **not_full)

        has_empty_activities = any(v.count() > 0 for v in [tonight_empty, tomorrow_empty])

        user_activities = Activity.objects.filter(
            place__group=group,
            participants__in=[user],
        ).order_by('date')

        tonight_user = user_activities.filter(**tonight)
        tomorrow_user = user_activities.filter(**tomorrow)

        tonight_not_full = base_tonight_not_full.exclude(participants__in=[user])
        tomorrow_not_full = base_tomorrow_not_full.exclude(participants__in=[user])

        has_user_activities = any([
            v.count() > 0 for v in [
                tonight_user,
                tomorrow_user,
                tonight_not_full,
                tomorrow_not_full,
            ]
        ])

        if has_empty_activities or has_user_activities:
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
