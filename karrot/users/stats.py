from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from karrot.activities.models import Activity
from karrot.groups.models import GroupMembership, GroupStatus


def get_users_stats():
    User = get_user_model()

    # These "active" users use the database inactive_at field (which means 30 days)
    active_users = User.objects.filter(groupmembership__in=GroupMembership.objects.active(), deleted=False).distinct()
    active_membership_count = GroupMembership.objects.active().count()
    active_users_count = active_users.count()
    active_memberships_per_active_user_avg = (
        active_membership_count / active_users_count if active_users_count > 0 else 0
    )

    fields = {
        "active_count": active_users_count,
        "active_unverified_count": active_users.filter(mail_verified=False).count(),
        "active_with_location_count": active_users.exclude(latitude=None).exclude(longitude=None).count(),
        "active_with_mobile_number_count": active_users.exclude(mobile_number="").count(),
        "active_with_description_count": active_users.exclude(description="").count(),
        "active_with_photo_count": active_users.exclude(photo="").count(),
        "active_memberships_per_active_user_avg": active_memberships_per_active_user_avg,
        "no_membership_count": User.objects.filter(groupmembership=None, deleted=False).count(),
        "deleted_count": User.objects.filter(deleted=True).count(),
    }

    for n in (1, 7, 30, 60, 90):
        active_users = User.objects.filter(
            groupmembership__in=GroupMembership.objects.exclude_playgrounds().active_within(days=n),
            deleted=False,
        ).distinct()
        now = timezone.now()
        activity_active_users = User.objects.filter(
            activities__in=Activity.objects.exclude_disabled()
            .filter(
                date__startswith__lt=now,
                date__startswith__gte=now - relativedelta(days=n),
            )
            .exclude(
                place__group__status=GroupStatus.PLAYGROUND,
            ),
            deleted=False,
        ).distinct()
        fields.update(
            {
                f"count_active_{n}d": active_users.count(),
                f"count_activity_active_{n}d": activity_active_users.count(),
            }
        )

    return fields


def get_user_language_stats():
    User = get_user_model()

    # These "active" users use the database inactive_at field (which means 30 days)
    active_users = User.objects.filter(groupmembership__in=GroupMembership.objects.active(), deleted=False).distinct()
    language_count = active_users.values("language").annotate(count=Count("language"))

    return {item["language"]: item["count"] for item in language_count}
