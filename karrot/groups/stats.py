from collections import defaultdict

from django.db.models import Count
from django.utils import timezone
from karrot.utils.influxdb_utils import write_points


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


def member_returned(membership):
    fields = {
        'group_member_returned': 1,
    }

    def get_seconds_to_now(date):
        return round((timezone.now() - date).total_seconds())

    if membership.removal_notification_at is not None:
        fields.update({
            'group_member_returned_seconds_since_marked_for_removal':
            get_seconds_to_now(membership.removal_notification_at)
        })
    else:
        fields.update({
            'group_member_returned_seconds_since_marked_as_inactive':
            get_seconds_to_now(membership.inactive_at)
        })

    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(membership.group),
        'fields': fields,
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
        activity_active_memberships = memberships.activity_active_within(days=n)
        fields.update({
            'count_active_{}d'.format(n): active_memberships.count(),
            'count_active_newcomers_{}d'.format(n): active_memberships.newcomers().count(),
            'count_active_editors_{}d'.format(n): active_memberships.editors().count(),
            'count_activity_active_{}d'.format(n): activity_active_memberships.count(),
            'count_activity_active_newcomers_{}d'.format(n): activity_active_memberships.newcomers().count(),
            'count_activity_active_editors_{}d'.format(n): activity_active_memberships.editors().count(),
        })

    notification_type_count = defaultdict(int)
    for membership in memberships.active_within(days=30):

        for t in membership.notification_types:
            notification_type_count[t] += 1

    for t, count in notification_type_count.items():
        fields.update({'count_active_30d_with_notification_type_{}'.format(t): count})

    return [{
        'measurement': 'karrot.group.members',
        'tags': group_tags(group),
        'fields': fields,
    }]


def get_group_places_stats(group):
    fields = {
        'count_total': group.places.count(),
    }

    for entry in group.places.values('status').annotate(count=Count('status')):
        # record one value per place status too
        fields['count_status_{}'.format(entry['status'])] = entry['count']

    return [{
        'measurement': 'karrot.group.places',
        'tags': group_tags(group),
        'fields': fields,
    }]
