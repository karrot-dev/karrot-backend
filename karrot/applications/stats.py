from django.db.models import Count
from django.utils import timezone
from karrot.utils.influxdb_utils import write_points

from karrot.groups.stats import group_tags


def application_status_update(application):
    tags = group_tags(application.group)
    fields = {
        'application_{}'.format(application.status): 1,
    }

    if application.status != 'pending':
        seconds = round((timezone.now() - application.created_at).total_seconds())
        fields['application_alive_seconds'] = seconds
        fields['application_{}_alive_seconds'.format(application.status)] = seconds
        tags['application_status'] = application.status

    write_points([{
        'measurement': 'karrot.events',
        'tags': tags,
        'fields': fields,
    }])


def get_application_stats(group):
    fields = {
        'count_total': group.application_set.count(),
    }

    for entry in group.application_set.values('status').annotate(count=Count('status')):
        fields['count_status_{}'.format(entry['status'])] = entry['count']

    return [{
        'measurement': 'karrot.group.applications',
        'tags': group_tags(group),
        'fields': fields,
    }]
