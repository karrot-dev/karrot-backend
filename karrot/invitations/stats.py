from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def invitation_created(invitation):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(invitation.group),
        'fields': {
            'invitation_created': 1
        },
    }])


def invitation_accepted(invitation):
    write_points([{
        'measurement': 'karrot.events',
        'tags': group_tags(invitation.group),
        'fields': {
            'invitation_accepted': 1
        },
    }])
