from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def issue_tags(issue):
    tags = group_tags(issue.group)
    tags.update(
        {"type": issue.type,}
    )
    return tags


def issue_created(issue):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": issue_tags(issue),
                "fields": {"issue_created": 1},
            }
        ]
    )


def voted(issue):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": issue_tags(issue),
                "fields": {"issue_vote": 1},
            }
        ]
    )


def vote_changed(issue):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": issue_tags(issue),
                "fields": {"issue_vote_changed": 1},
            }
        ]
    )


def vote_deleted(issue):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": issue_tags(issue),
                "fields": {"issue_vote_deleted": 1},
            }
        ]
    )


def get_issue_stats(group):
    fields = {
        "count_total": group.issues.count(),
        "count_ongoing": group.issues.ongoing().count(),
        "count_decided": group.issues.decided().count(),
        "count_cancelled": group.issues.cancelled().count(),
    }

    return [
        {
            "measurement": "karrot.group.issues",
            "tags": group_tags(group),
            "fields": fields,
        }
    ]
