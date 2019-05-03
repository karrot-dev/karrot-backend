from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from karrot.groups.models import GroupMembership, GroupStatus
from karrot.pickups.models import PickupDate
from karrot.webhooks.models import EmailEvent


def get_users_stats():
    User = get_user_model()

    # These "active" users use the database inactive_at field (which means 30 days)
    active_users = User.objects.filter(groupmembership__in=GroupMembership.objects.active(), deleted=False).distinct()
    active_membership_count = GroupMembership.objects.active().count()
    active_users_count = active_users.count()

    fields = {
        'active_count': active_users_count,
        'active_unverified_count': active_users.filter(mail_verified=False).count(),
        'active_ignored_email_count': active_users.filter(email__in=EmailEvent.objects.ignored_addresses()).count(),
        'active_with_location_count': active_users.exclude(latitude=None).exclude(longitude=None).count(),
        'active_with_mobile_number_count': active_users.exclude(mobile_number='').count(),
        'active_with_description_count': active_users.exclude(description='').count(),
        'active_with_photo_count': active_users.exclude(photo='').count(),
        'active_memberships_per_active_user_avg': active_membership_count / active_users_count,
        'no_membership_count': User.objects.filter(groupmembership=None, deleted=False).count(),
        'deleted_count': User.objects.filter(deleted=True).count(),
    }

    for n in (1, 7, 30, 60, 90):
        active_users = User.objects.filter(
            groupmembership__in=GroupMembership.objects.exclude_playgrounds().active_within(days=n),
            deleted=False,
        ).distinct()
        now = timezone.now()
        pickup_active_users = User.objects.filter(
            pickup_dates__in=PickupDate.objects.exclude_disabled().filter(
                date__startswith__lt=now,
                date__startswith__gte=now - relativedelta(days=n)
            ).exclude(
                place__group__status=GroupStatus.PLAYGROUND,
            ),
            deleted=False
        ).distinct()
        fields.update({
            'count_active_{}d'.format(n): active_users.count(),
            'count_pickup_active_{}d'.format(n): pickup_active_users.count(),
        })

    return fields
