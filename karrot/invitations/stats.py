from karrot.groups.stats import group_tags
from karrot.utils.influxdb_utils import write_points


def invitation_created(invitation):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(invitation.group),
                "fields": {"invitation_created": 1},
            }
        ]
    )


def invitation_accepted(invitation):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(invitation.group),
                "fields": {"invitation_accepted": 1},
            }
        ]
    )
