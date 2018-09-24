from django.utils import timezone
from influxdb_metrics.loader import write_points

from foodsaving.groups.models import Group
from foodsaving.groups.stats import group_tags


def notification_tags(notification):
    tags = {
        'notification_type': notification.type,
    }
    group = Group.objects.get(id=notification.context['group'])
    tags.update(group_tags(group))
    return tags


def notification_clicked(notification):
    write_points([{
        'measurement': 'karrot.events',
        'tags': notification_tags(notification),
        'fields': {
            'notification_clicked': 1,
            'notification_clicked_seconds': (timezone.now() - notification.created_at).seconds
        },
    }])


def notification_created(notification):
    write_points([{
        'measurement': 'karrot.events',
        'tags': notification_tags(notification),
        'fields': {
            'notification_created': 1
        },
    }])
