from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.timezone import get_current_timezone

from config import settings
from karrot.conversations.models import ConversationMessage
from karrot.groups.models import Group, GroupNotificationType, GroupMembership
from karrot.pickups.models import PickupDate, Feedback
from karrot.utils.email_utils import prepare_email
from karrot.utils.frontend_urls import group_wall_url, group_settings_url, group_summary_unsubscribe_url


def prepare_group_summary_data(group, from_date, to_date):
    new_users = group.members.filter(
        groupmembership__created_at__gte=from_date,
        groupmembership__created_at__lt=to_date,
    ).all()

    pickup_dates = PickupDate.objects.in_group(group).exclude_disabled().filter(
        date__startswith__gte=from_date, date__startswith__lt=to_date
    ).annotate_num_collectors()

    pickups_done_count = pickup_dates.done().count()

    pickups_missed_count = pickup_dates.missed().count()

    feedbacks = Feedback.objects.filter(
        created_at__gte=from_date,
        created_at__lt=to_date,
        about__place__group=group,
    )

    messages = ConversationMessage.objects.exclude_replies().filter(
        conversation__target_type=ContentType.objects.get_for_model(Group),
        conversation__target_id=group.id,
        created_at__gte=from_date,
        created_at__lt=to_date,
    )

    data = {
        # minus one second so it's displayed as the full day
        'to_date': to_date - relativedelta(seconds=1),
        'from_date': from_date,
        'group': group,
        'new_users': new_users,
        'pickups_done_count': pickups_done_count,
        'pickups_missed_count': pickups_missed_count,
        'feedbacks': feedbacks,
        'messages': messages,
        'settings_url': group_settings_url(group),
    }

    data['has_activity'] = any(data[field] > 0 for field in ['pickups_done_count', 'pickups_missed_count']) or \
        any(len(data[field]) > 0 for field in ['feedbacks', 'messages', 'new_users'])

    return data


def prepare_group_summary_emails(group, context):
    """Prepares one email per language"""

    members = group.members.filter(
        groupmembership__in=GroupMembership.objects.active().
        with_notification_type(GroupNotificationType.WEEKLY_SUMMARY)
    ).exclude(groupmembership__user__in=get_user_model().objects.unverified_or_ignored())

    return [
        prepare_email(
            template='group_summary',
            tz=group.timezone,
            context={
                'unsubscribe_url': group_summary_unsubscribe_url(member, group),
                **context,
            },
            to=[member.email],
            language=member.language,
        ) for member in members
    ]


def calculate_group_summary_dates(group):
    with timezone.override(group.timezone):
        tz = get_current_timezone()

        # midnight last night in the groups local timezone
        midnight = tz.localize(timezone.now().replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0))

        # 7 days before that
        from_date = midnight - relativedelta(days=7)

        # a week after from date
        to_date = from_date + relativedelta(days=7)

        return from_date, to_date


def prepare_user_inactive_in_group_email(user, group):
    return prepare_email(
        template='user_inactive_in_group',
        user=user,
        tz=group.timezone,
        context={
            'group_name': group.name,
            'group_url': group_wall_url(group),
            'num_days_inactive': settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP,
        },
    )


def prepare_user_removal_from_group_email(user, group):
    return prepare_email(
        template='user_removal_from_group',
        user=user,
        tz=group.timezone,
        context={
            'group_name': group.name,
            'group_url': group_wall_url(group),
            'num_months_inactive': settings.NUMBER_OF_INACTIVE_MONTHS_UNTIL_REMOVAL_FROM_GROUP_NOTIFICATION,
            'num_removal_days': settings.NUMBER_OF_DAYS_AFTER_REMOVAL_NOTIFICATION_WE_ACTUALLY_REMOVE_THEM,
        },
    )


def prepare_user_became_editor_email(user, group):
    return prepare_email(
        template='user_became_editor',
        user=user,
        tz=group.timezone,
        context={
            'group_name': group.name,
            'group_url': group_wall_url(group),
        },
    )
