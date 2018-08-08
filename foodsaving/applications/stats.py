from django.db.models import Count
from django.utils import timezone
from influxdb_metrics.loader import write_points


def application_status_update(application):
    fields = {
        'application_{}'.format(application.status): 1,
    }

    if application.status != 'pending':
        fields['application_{}_seconds'.format(application.status)] = (timezone.now() - application.created_at).seconds

    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'group': str(application.group.id)
        },
        'fields': fields,
    }])


def get_group_application_stats(group):
    fields = {
        'count_total': group.groupapplication_set.count(),
    }

    for entry in group.groupapplication_set.values('status').annotate(count=Count('status')):
        fields['count_status_{}'.format(entry['status'])] = entry['count']

    return [{
        'measurement': 'karrot.group.applications',
        'tags': {
            'group': str(group.id),
        },
        'fields': fields,
    }]
