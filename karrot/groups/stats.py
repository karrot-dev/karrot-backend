import re
from collections import defaultdict

import unidecode
from django.db.models import Count
from django.utils import timezone

from karrot.utils.influxdb_utils import write_points


def group_tags(group):
    return {
        "group": str(group.id),
        "group_status": group.status,
    }


def trust_tags(trust):
    tags = group_tags(trust.membership.group)
    tags.update({"trust_role": trust.role})
    return tags


def group_joined(group):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(group),
                "fields": {"group_joined": 1},
            }
        ]
    )


def group_left(group):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(group),
                "fields": {"group_left": 1},
            }
        ]
    )


def member_returned(membership):
    fields = {
        "group_member_returned": 1,
    }

    def get_seconds_to_now(date):
        return round((timezone.now() - date).total_seconds())

    if membership.removal_notification_at is not None:
        fields.update(
            {
                "group_member_returned_seconds_since_marked_for_removal": get_seconds_to_now(
                    membership.removal_notification_at
                )
            }
        )
    else:
        fields.update(
            {"group_member_returned_seconds_since_marked_as_inactive": get_seconds_to_now(membership.inactive_at)}
        )

    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(membership.group),
                "fields": fields,
            }
        ]
    )


def group_activity(group):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(group),
                "fields": {"group_activity": 1},
            }
        ]
    )


def group_summary_email(group, **extra_fields):
    write_points(
        [
            {
                "measurement": "karrot.email.group_summary",
                "tags": group_tags(group),
                "fields": {"value": 1, **extra_fields},
            }
        ]
    )


def trust_given(trust):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": trust_tags(trust),
                "fields": {"trust_given": 1},
            }
        ]
    )


def trust_revoked(trust):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": trust_tags(trust),
                "fields": {"trust_revoked": 1},
            }
        ]
    )


def member_became_editor(group):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(group),
                "fields": {"member_became_editor": 1},
            }
        ]
    )


def user_lost_editor_role(group):
    write_points(
        [
            {
                "measurement": "karrot.events",
                "tags": group_tags(group),
                "fields": {"user_lost_editor_role": 1},
            }
        ]
    )


def get_group_members_stats(group):
    memberships = group.groupmembership_set

    fields = {
        "count_total": memberships.count(),
        "count_newcomers_total": memberships.newcomers().count(),
        "count_editors_total": memberships.editors().count(),
    }

    for n in (1, 7, 30, 60, 90):
        active_memberships = memberships.active_within(days=n)
        activity_active_memberships = memberships.activity_active_within(days=n)
        fields.update(
            {
                f"count_active_{n}d": active_memberships.count(),
                f"count_active_newcomers_{n}d": active_memberships.newcomers().count(),
                f"count_active_editors_{n}d": active_memberships.editors().count(),
                f"count_activity_active_{n}d": activity_active_memberships.count(),
                f"count_activity_active_newcomers_{n}d": activity_active_memberships.newcomers().count(),
                f"count_activity_active_editors_{n}d": activity_active_memberships.editors().count(),
            }
        )

    notification_type_count = defaultdict(int)
    for membership in memberships.active_within(days=30):
        for t in membership.notification_types:
            notification_type_count[t] += 1

    for t, count in notification_type_count.items():
        fields.update({f"count_active_30d_with_notification_type_{t}": count})

    return [
        {
            "measurement": "karrot.group.members",
            "tags": group_tags(group),
            "fields": fields,
        }
    ]


# not sure what is actually invalid or not, but let's keep it simple...
STATS_KEY_INVALID_CHARS_RE = re.compile(r"[^a-zA-Z0-9_\-.]")


def get_group_places_stats(group):
    fields = {
        "count_total": group.places.count(),
    }

    def convert_status_name(name: str) -> str:
        """Status name might be user entered now, so we should convert anything funny"""
        # lowercasing means the new place statuses match the old ones
        # (enum ones vs the new custom foreign key implementation)
        name = name.lower()

        # unidecode has various caveats, does not do locale-aware conversion
        # e.g. German "ä" goes to "a" not "ae"
        # https://pypi.org/project/Unidecode/ explains why it's difficult
        # it should be fine for our purposes :)
        name = unidecode.unidecode(name)

        # replace anything else funny with a _
        name = STATS_KEY_INVALID_CHARS_RE.sub("_", name)

        return name

    for entry in (
        group.places.select_related("status")
        .filter(archived_at__isnull=True)
        .values("status__name")
        .annotate(count=Count("status"))
    ):
        # record one value per place status too
        # lowercase the status name to keep consistent with previous approach
        fields["count_status_{}".format(convert_status_name(entry["status__name"]))] = entry["count"]

    fields["count_status_archived"] = group.places.filter(archived_at__isnull=False).count()

    return [
        {
            "measurement": "karrot.group.places",
            "tags": group_tags(group),
            "fields": fields,
        }
    ]
