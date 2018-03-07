from foodsaving.utils.email_utils import prepare_email


def prepare_pickup_notification_email(
    user,
    group,
    tonight_date,
    tomorrow_date,
    user_pickups_tonight=None,
    group_pickups_tonight_empty=None,
    group_pickups_tonight_not_full=None,
    user_pickups_tomorrow=None,
    group_pickups_tomorrow_empty=None,
    group_pickups_tomorrow_not_full=None,
):
    has_pickups_tonight = any([
        items is not None and len(items) > 0 for items in [
            user_pickups_tonight,
            group_pickups_tonight_empty,
            group_pickups_tonight_not_full,
        ]
    ])
    has_pickups_tomorrow = any([
        items is not None and len(items) > 0 for items in [
            user_pickups_tomorrow,
            group_pickups_tomorrow_empty,
            group_pickups_tomorrow_not_full,
        ]
    ])
    return prepare_email(
        template='pickup_notification',
        user=user,
        context={
            'group': group,
            'tonight_date':tonight_date,
            'tomorrow_date': tomorrow_date,
            'has_pickups_tonight': has_pickups_tonight,
            'user_pickups_tonight': user_pickups_tonight,
            'group_pickups_tonight_empty': group_pickups_tonight_empty,
            'group_pickups_tonight_not_full': group_pickups_tonight_not_full,
            'has_pickups_tomorrow': has_pickups_tomorrow,
            'user_pickups_tomorrow': user_pickups_tomorrow,
            'group_pickups_tomorrow_empty': group_pickups_tomorrow_empty,
            'group_pickups_tomorrow_not_full': group_pickups_tomorrow_not_full,
        }
    )
