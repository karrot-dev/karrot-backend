from karrot.utils.email_utils import prepare_email
from karrot.utils.frontend_urls import pickup_notification_unsubscribe_url


def prepare_pickup_notification_email(
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
    has_pickups_tonight = any([
        items is not None and len(items) > 0 for items in [
            tonight_user,
            tonight_empty,
            tonight_not_full,
        ]
    ])
    has_pickups_tomorrow = any([
        items is not None and len(items) > 0 for items in [
            tomorrow_user,
            tomorrow_empty,
            tomorrow_not_full,
        ]
    ])

    unsubscribe_url = pickup_notification_unsubscribe_url(user, group)

    return prepare_email(
        template='pickup_notification',
        user=user,
        tz=group.timezone,
        context={
            'unsubscribe_url': unsubscribe_url,
            'group': group,
            'tonight_date': tonight_date,
            'tomorrow_date': tomorrow_date,
            'has_pickups_tonight': has_pickups_tonight,
            'has_pickups_tomorrow': has_pickups_tomorrow,
            'tonight_user': tonight_user,
            'tonight_empty': tonight_empty,
            'tonight_not_full': tonight_not_full,
            'tomorrow_user': tomorrow_user,
            'tomorrow_empty': tomorrow_empty,
            'tomorrow_not_full': tomorrow_not_full,
        },
        stats_category='pickup_notification',
    )
