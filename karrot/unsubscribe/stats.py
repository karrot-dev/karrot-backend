from karrot.utils.influxdb_utils import write_points

from karrot.groups.stats import group_tags


def unsubscribed(group, choice, notification_type):
    tags = {
        'choice': choice,
    }
    if group:
        tags.update(group_tags(group))
    if notification_type:
        tags.update({
            'notification_type': notification_type,
        })

    write_points([{
        'measurement': 'karrot.unsubscribe',
        'tags': tags,
        'fields': {
            'token_unsubscribe': 1
        },
    }])
