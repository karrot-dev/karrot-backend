from influxdb_metrics.loader import write_points

from foodsaving.groups.stats import group_tags


def pickup_tags(pickup):
    tags = group_tags(pickup.store.group)
    tags.update({
        'store': str(pickup.store.id),
    })
    return tags


def pickup_joined(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_joined': 1
        },
    }])


def pickup_left(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_left': 1
        },
    }])


def pickup_done(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_done': 1
        },
    }])


def pickup_missed(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_missed': 1
        },
    }])


def pickup_cancelled(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_cancelled': 1
        },
    }])


def pickup_uncancelled(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_uncancelled': 1
        },
    }])


def feedback_given(feedback):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(feedback.about),
        'fields': {
            'feedback': 1
        },
    }])


def pickup_notification_email(group, **kwargs):
    write_points([{
        'measurement': 'karrot.email.pickup_notification',
        'tags': group_tags(group),
        'fields': {
            'value': 1,
            **kwargs
        },
    }])
