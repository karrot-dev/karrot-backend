from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def activity_tags(activity):
    tags = group_tags(activity.place.group)
    tags.update({
        'place': str(activity.place.id),
    })
    return tags


def activity_joined(activity):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': {
            'activity_joined': 1
        },
    }])


def activity_left(activity):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': {
            'activity_left': 1
        },
    }])


def activity_done(activity):
    participants_count = activity.participants.count()
    fields = {
        'activity_done': 1,
        'activity_done_slots_joined': participants_count,
    }

    if activity.max_participants is not None and activity.max_participants > 0:
        fields.update({
            'activity_done_slots_total': activity.max_participants,
            'activity_done_slots_percentage': participants_count / activity.max_participants,
        })

    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': fields,
    }])


def activity_missed(activity):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': {
            'activity_missed': 1
        },
    }])


def activity_disabled(activity):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': {
            'activity_disabled': 1
        },
    }])


def activity_enabled(activity):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(activity),
        'fields': {
            'activity_enabled': 1
        },
    }])


def feedback_given(feedback):
    write_points([{
        'measurement': 'karrot.events',
        'tags': activity_tags(feedback.about),
        'fields': {
            'feedback': 1
        },
    }])


def activity_notification_email(group, **kwargs):
    write_points([{
        'measurement': 'karrot.email.activity_notification',
        'tags': group_tags(group),
        'fields': {
            'value': 1,
            **kwargs
        },
    }])
