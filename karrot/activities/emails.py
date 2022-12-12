from karrot.utils.email_utils import prepare_email
from karrot.utils.frontend_urls import activity_notification_unsubscribe_url


def prepare_activity_notification_email(
    user,
    group,
    tonight_date,
    tomorrow_date,
    tonight_user=None,
    tonight_empty=None,
    tonight_not_full=None,
    tomorrow_user=None,
    tomorrow_empty=None,
    tomorrow_not_full=None,
):
    has_activities_tonight = any([
        items is not None and len(items) > 0 for items in [
            tonight_user,
            tonight_empty,
            tonight_not_full,
        ]
    ])
    has_activities_tomorrow = any([
        items is not None and len(items) > 0 for items in [
            tomorrow_user,
            tomorrow_empty,
            tomorrow_not_full,
        ]
    ])

    unsubscribe_url = activity_notification_unsubscribe_url(user, group)

    return prepare_email(
        template='activity_notification',
        user=user,
        group=group,
        tz=group.timezone,
        context={
            'unsubscribe_url': unsubscribe_url,
            'group': group,
            'tonight_date': tonight_date,
            'tomorrow_date': tomorrow_date,
            'has_activities_tonight': has_activities_tonight,
            'has_activities_tomorrow': has_activities_tomorrow,
            'tonight_user': tonight_user,
            'tonight_empty': tonight_empty,
            'tonight_not_full': tonight_not_full,
            'tomorrow_user': tomorrow_user,
            'tomorrow_empty': tomorrow_empty,
            'tomorrow_not_full': tomorrow_not_full,
        },
        stats_category='activity_notification',
    )


def prepare_participant_removed_email(
    user,
    place,
    activities,
    removed_by,
    message,
):

    group = place.group

    return prepare_email(
        template='participant_removed',
        user=user,
        group=group,
        tz=group.timezone,
        context={
            'group': group,
            'place': place,
            'activities': activities,
            'removed_by': removed_by,
            'message': message,
        },
        stats_category='participant_removed',
    )
