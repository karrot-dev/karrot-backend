from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.utils import timezone
from influxdb_metrics.loader import write_points


def group_joined(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'group': str(group.id)
        },
        'fields': {
            'group_joined': 1
        },
    }])


def group_left(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'group': str(group.id)
        },
        'fields': {
            'group_left': 1
        },
    }])


def group_activity(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'group': str(group.id)
        },
        'fields': {
            'group_activity': 1
        },
    }])


def group_summary_email(group, **extra_fields):
    write_points([{
        'measurement': 'karrot.email.group_summary',
        'tags': {
            'group': str(group.id)
        },
        'fields': {
            'value': 1,
            **extra_fields
        },
    }])


def get_group_members_stats(group):
    now = timezone.now()

    def members_active_within(**kwargs):
        return group.members.filter(groupmembership__lastseen_at__gte=now - relativedelta(**kwargs)).count()

    return [{
        'measurement': 'karrot.group.members',
        'tags': {
            'group': str(group.id)
        },
        'fields': {
            'count_total': group.members.count(),
            'count_active_1d': members_active_within(days=1),
            'count_active_7d': members_active_within(days=7),
            'count_active_30d': members_active_within(days=30),
            'count_active_60d': members_active_within(days=60),
            'count_active_90d': members_active_within(days=90),
        },
    }]


def get_group_stores_stats(group):
    fields = {
        'count_total': group.store.count(),
    }

    for entry in group.store.values('status').annotate(count=Count('status')):
        # record one value per store status too
        fields['count_status_{}'.format(entry['status'])] = entry['count']

    return [{
        'measurement': 'karrot.group.stores',
        'tags': {
            'group': str(group.id),
        },
        'fields': fields,
    }]
