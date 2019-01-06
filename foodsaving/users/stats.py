from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from foodsaving.groups.models import GroupMembership
from foodsaving.pickups.models import PickupDate
from foodsaving.webhooks.models import EmailEvent


def get_users_stats():
    User = get_user_model()

    active_users = User.objects.filter(groupmembership__in=GroupMembership.objects.active(), deleted=False).distinct()
    active_membership_count = GroupMembership.objects.active().count()
    active_users_count = active_users.count()

    done_pickup_filter = {'pickup_dates__in':PickupDate.objects.exclude_disabled().filter(date__lt=timezone.now())}
    pickup_active_users = active_users.filter(**done_pickup_filter)
    pickup_users = User.objects.filter(**done_pickup_filter)

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
        'pickup_active_count': pickup_active_users.count(),
        'pickup_count': pickup_users.count(),
    }

    return fields
