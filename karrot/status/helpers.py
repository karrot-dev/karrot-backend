from django.db.models import F, Count, Q, Case, When, BooleanField

from karrot.applications.models import ApplicationStatus
from karrot.conversations.models import ConversationParticipant, ConversationThreadParticipant
from karrot.groups.models import Group
from karrot.notifications.models import Notification
from karrot.pickups.models import PickupDate
from karrot.places.models import PlaceStatus


def unseen_notification_count(user):
    return Notification.objects \
        .filter(
            user=user,
            created_at__gt=F('user__notificationmeta__marked_at')
        ) \
        .count()


def unread_conversations(user):
    threads = ConversationThreadParticipant.objects.filter(user=user).annotate_unread_replies_count().filter(
        unread_replies_count__gt=0
    ).aggregate(
        unread=Count('id'),
        unseen=Count(
            'id', filter=Q(thread__latest_message__created_at__gt=F('user__conversationmeta__threads_marked_at'))
        )
    )
    participants = list(
        ConversationParticipant.objects.filter(user=user).annotate_unread_message_count().filter(
            unread_message_count__gt=0
        ).select_related('conversation', 'conversation__target_type').annotate(
            is_unseen=Case(
                When(
                    conversation__latest_message__created_at__gt=F('user__conversationmeta__conversations_marked_at'),
                    then=True
                ),
                default=False,
                output_field=BooleanField()
            )
        )
    )

    groups = {}
    places = {}
    unseen_conversation_count = 0
    unseen_thread_count = threads['unseen']

    for p in participants:
        conversation = p.conversation
        target_id = conversation.target_id
        t = conversation.type()
        if t == 'group':
            groups[target_id] = {'unread_wall_message_count': p.unread_message_count}
        elif t == 'place':
            places[target_id] = {'unread_wall_message_count': p.unread_message_count}

        if p.is_unseen:
            unseen_conversation_count += 1

    return {
        'unseen_conversation_count': unseen_conversation_count,
        'unseen_thread_count': unseen_thread_count,
        'has_unread_conversations_or_threads': len(participants) + threads['unread'] > 0,
        'groups': groups,
        'places': places,
    }


def pending_applications(user):
    return Group.objects.filter(members=user).annotate(
        pending_application_count=Count('application', filter=Q(application__status=ApplicationStatus.PENDING.value))
    ).values_list('id', 'pending_application_count')


def get_feedback_possible(user):
    return Group.objects.filter(members=user).annotate(
        feedback_possible=Count(
            'places__pickup_dates',
            filter=Q(
                places__pickup_dates__in=PickupDate.objects.only_feedback_possible(user),
                places__status=PlaceStatus.ACTIVE.value
            )
        )
    ).values_list('id', 'feedback_possible')
