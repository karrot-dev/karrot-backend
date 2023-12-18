from collections import defaultdict

from babel.dates import format_datetime, format_time
from dateutil.relativedelta import relativedelta
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Q, QuerySet
from django.utils import timezone, translation
from django.utils.text import Truncator
from django.utils.timezone import get_current_timezone
from django.utils.translation import get_language, to_locale
from django.utils.translation import gettext as _
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from karrot.activities import stats
from karrot.activities.emails import prepare_activity_notification_email, prepare_participant_removed_email
from karrot.activities.models import Activity, ActivityParticipant, ActivitySeries, ActivityType, ParticipantType
from karrot.groups.models import Group, GroupMembership, GroupNotificationType
from karrot.notifications.models import Notification, NotificationType
from karrot.places.models import Place, PlaceStatus
from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.tasks import notify_subscribers
from karrot.users.models import User
from karrot.utils import frontend_urls, stats_utils
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
    if activity.is_disabled:
        return

    user = participant.user
    language = user.language
    tz = activity.group.timezone

    with translation.override(language), timezone.override(tz):
        if is_past(activity.date.start):
            return

        subscriptions = WebPushSubscription.objects.filter(user=user)
        if subscriptions.count() == 0:
            return

        emoji = "⏰"

        if is_today(activity.date.start):
            when = format_time(
                activity.date.start,
                format="short",
                locale=translation.to_locale(language),
                tzinfo=tz,
            )
        else:
            when = format_datetime(
                activity.date.start,
                format="medium",  # short gives US date format in English, is confusing!
                locale=translation.to_locale(language),
                tzinfo=tz,
            )

        where = ", ".join(part for part in [activity.place.name, activity.place.address] if part)

        title = _("Upcoming %(activity_type)s") % {"activity_type": activity.activity_type.get_translated_name()}
        title = f"{emoji} {title}!"

        body = Truncator(" / ".join(part for part in [when, where, activity.description] if part)).chars(num=1000)

        click_action = frontend_urls.activity_detail_url(activity)

        notify_subscribers(
            subscriptions=subscriptions,
            title=title,
            body=body,
            url=click_action,
            tag=f"activity:{activity.id}",
        )


@db_task()
def notify_participant_removals(
    activity_type_id,
    place_id,
    activities_data,  # [<dict data of activity info>, ...]
    participants,  # [{'user':<userid>,'activity':<activityid>}, ...],
    message,
    removed_by_id,
    history_id,
):
    removed_by = User.objects.get(id=removed_by_id)
    activity_type = ActivityType.objects.get(id=activity_type_id)

    place = Place.objects.get(id=place_id)
    group = place.group

    activities_by_id = {}
    for entry in activities_data:
        # activities doesn't include related fields, so flesh it out a bit
        activities_by_id[entry["id"]] = {
            **entry,
            "activity_type": ActivityType.objects.get(id=entry["activity_type"]),
            "place": Place.objects.get(id=entry["place"]),
        }

    # collect activities affected per-user
    by_user = defaultdict(list)
    for entry in participants:
        by_user[entry["user"]].append(activities_by_id[entry["activity"]])

    for user_id in by_user.keys():
        activities_for_user = by_user[user_id]
        user = User.objects.get(id=user_id)

        language = user.language
        tz = group.timezone

        with translation.override(language), timezone.override(tz):
            # email them
            prepare_participant_removed_email(
                user,
                place,
                activities_for_user,
                removed_by,
                message,
            ).send()

            # send a notification and push message *per activity* so the user can see the details
            for activity in activities_for_user:
                Notification.objects.create(
                    type=NotificationType.PARTICIPANT_REMOVED.value,
                    user=user,
                    context={
                        "activity_type": activity_type.id,
                        "place": place.id,
                        "group": group.id,
                        "activity_date": DjangoJSONEncoder().default(activity["date"].start),
                        "removed_by": removed_by.id,
                        "history": history_id,
                    },
                )

                subscriptions = WebPushSubscription.objects.filter(user=user)
                activity_type_name = activity["activity_type"].get_translated_name()
                formatted_date_time = format_datetime(
                    activity["date"].start,
                    format="medium",
                    locale=to_locale(get_language()),
                    tzinfo=get_current_timezone(),
                )
                title = _("%(activity_type)s no longer available - %(date_time)s") % {
                    "activity_type": activity_type_name,
                    "date_time": formatted_date_time,
                }
                body = removed_by.display_name + ":" + Truncator(message).chars(num=1000)
                if subscriptions.count() > 0:
                    notify_subscribers(
                        subscriptions=subscriptions,
                        title=title,
                        body=body,
                        url=frontend_urls.history_url(history_id),
                    )


@db_periodic_task(crontab(minute="*"))  # every minute
def process_finished_activities():
    with timer() as t:
        Activity.objects.process_finished_activities()
    stats_utils.periodic_task("activities__process_finished_activities", seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute=0))  # every hour
def update_activities():
    with timer() as t:
        ActivitySeries.objects.update_activities()
    stats_utils.periodic_task("activities__update_activities", seconds=t.elapsed_seconds)


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
                        group=data["group"], **{k: v.count() for k, v in data.items() if isinstance(v, QuerySet)}
                    )

    stats_utils.periodic_task("activities__daily_activity_notifications", seconds=t.elapsed_seconds)


def fetch_activity_notification_data_for_group(group):
    results = []
    localnow = timezone.localtime()

    midnight = localnow.replace(hour=0, minute=0, second=0, microsecond=0) + relativedelta(days=1)
    midnight_tomorrow = midnight + relativedelta(days=1)

    tonight = {"date__startswith__gte": localnow, "date__startswith__lt": midnight}
    tomorrow = {"date__startswith__gte": midnight, "date__startswith__lt": midnight_tomorrow}

    empty = {"num_participants": 0}
    not_full = {
        "participant_types__in": ParticipantType.objects.annotate_num_participants().filter(
            Q(num_participants__gt=0) & (Q(max_participants=None) | Q(num_participants__lt=F("max_participants"))),
        )
    }

    group_activities = (
        Activity.objects.exclude_disabled()
        .annotate_num_participants()
        .filter(
            place__status=PlaceStatus.ACTIVE.value,
            place__group=group,
        )
        .order_by("date")
    )

    users = group.members.filter(
        groupmembership__in=GroupMembership.objects.active().with_notification_type(
            GroupNotificationType.DAILY_ACTIVITY_NOTIFICATION
        ),
    ).exclude(
        groupmembership__user__in=User.objects.unverified(),
    )

    for user in users:
        membership = group.groupmembership_set.get(user=user)

        activities = group_activities.filter(
            participant_types__role__in=membership.roles,
        ).filter(
            # only the places they subscribed to
            place__placesubscription__user=user,
        )

        tonight_empty = activities.filter(**tonight, **empty)
        tomorrow_empty = activities.filter(**tomorrow, **empty)
        base_tonight_not_full = activities.filter(**tonight, **not_full)
        base_tomorrow_not_full = activities.filter(**tomorrow, **not_full)

        has_empty_activities = any(v.count() > 0 for v in [tonight_empty, tomorrow_empty])

        joined_activities = Activity.objects.filter(
            place__group=group,
            participants__in=[user],
        ).order_by("date")

        tonight_user = joined_activities.filter(**tonight)
        tomorrow_user = joined_activities.filter(**tomorrow)

        tonight_not_full = base_tonight_not_full.exclude(participants__in=[user])
        tomorrow_not_full = base_tomorrow_not_full.exclude(participants__in=[user])

        has_user_activities = any(
            v.count() > 0
            for v in [
                tonight_user,
                tomorrow_user,
                tonight_not_full,
                tomorrow_not_full,
            ]
        )

        if has_empty_activities or has_user_activities:
            results.append(
                {
                    "user": user,
                    "group": group,
                    "tonight_date": localnow,
                    "tomorrow_date": midnight,
                    "tonight_user": tonight_user,
                    "tonight_empty": tonight_empty,
                    "tonight_not_full": tonight_not_full,
                    "tomorrow_user": tomorrow_user,
                    "tomorrow_empty": tomorrow_empty,
                    "tomorrow_not_full": tomorrow_not_full,
                }
            )

    return results
