from django.db.models import Count
from influxdb_metrics.loader import write_points


def group_tags(group):
    return {
        'group': str(group.id),
        'group_status': group.status,
    }


def group_joined(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(group),
        'fields': {
            'group_joined': 1
        },
    }])


def group_left(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(group),
        'fields': {
            'group_left': 1
        },
    }])


def group_activity(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(group),
        'fields': {
            'group_activity': 1
        },
    }])


def group_summary_email(group, **extra_fields):
    write_points([{
        'measurement': 'karrot.email.group_summary',
        'tags': group_tags(group),
        'fields': {
            'value': 1,
            **extra_fields
        },
    }])


def trust_given(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(group),
        'fields': {
            'trust_given': 1
        },
    }])


def member_became_editor(group):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(group),
        'fields': {
            'member_became_editor': 1
        },
    }])


def get_group_members_stats(group):

    memberships = group.groupmembership_set

    fields = {
        'count_total': memberships.count(),
        'count_newcomers_total': memberships.newcomers().count(),
        'count_editors_total': memberships.editors().count(),
    }

    for n in (1, 7, 30, 60, 90):
        active_memberships = memberships.active_within(days=n)
        pickup_active_memberships = memberships.pickup_active_within(days=n)
        fields.update({
            'count_active_{}d'.format(n): active_memberships.count(),
            'count_active_newcomers_{}d'.format(n): active_memberships.newcomers().count(),
            'count_active_editors_{}d'.format(n): active_memberships.editors().count(),
            'count_pickup_active_{}d'.format(n): pickup_active_memberships.count(),
            'count_pickup_active_newcomers_{}d'.format(n): pickup_active_memberships.newcomers().count(),
            'count_pickup_active_editors_{}d'.format(n): pickup_active_memberships.editors().count(),
        })

    return [{
        'measurement': 'karrot.group.members',
        'tags': group_tags(group),
        'fields': fields,
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
        'tags': group_tags(group),
        'fields': fields,
    }]
