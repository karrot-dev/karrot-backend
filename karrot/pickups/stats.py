from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def pickup_tags(pickup):
    tags = group_tags(pickup.place.group)
    tags.update({
        'place': str(pickup.place.id),
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
    collectors_count = pickup.collectors.count()
    fields = {
        'pickup_done': 1,
        'pickup_done_slots_joined': collectors_count,
    }

    if pickup.max_collectors > 0:
        fields.update({
            'pickup_done_slots_total': pickup.max_collectors,
            'pickup_done_slots_percentage': collectors_count / pickup.max_collectors,
        })

    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': fields,
    }])


def pickup_missed(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_missed': 1
        },
    }])


def pickup_disabled(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_disabled': 1
        },
    }])


def pickup_enabled(pickup):
    write_points([{
        'measurement': 'karrot.events',
        'tags': pickup_tags(pickup),
        'fields': {
            'pickup_enabled': 1
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
