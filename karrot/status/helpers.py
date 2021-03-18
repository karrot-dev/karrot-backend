from collections import defaultdict
from django.db.models import F, Count, Q, Case, When, BooleanField
from rest_framework import serializers

from karrot.applications.models import ApplicationStatus
from karrot.conversations.models import ConversationParticipant, ConversationThreadParticipant
from karrot.groups.models import Group
from karrot.notifications.models import Notification
from karrot.activities.models import Activity
from karrot.places.models import PlaceStatusOld


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
            'places__activities',
            filter=Q(
                places__activities__in=Activity.objects.only_feedback_possible(user),
                places__status=PlaceStatusOld.ACTIVE.value
            )
        )
    ).values_list('id', 'feedback_possible')


class StatusSerializer(serializers.Serializer):
    unseen_conversation_count = serializers.SerializerMethodField()
    unseen_thread_count = serializers.SerializerMethodField()
    has_unread_conversations_or_threads = serializers.SerializerMethodField()
    unseen_notification_count = serializers.IntegerField()
    groups = serializers.SerializerMethodField()
    places = serializers.SerializerMethodField()

    @staticmethod
    def get_unseen_conversation_count(data):
        return data['conversations']['unseen_conversation_count']

    @staticmethod
    def get_unseen_thread_count(data):
        return data['conversations']['unseen_thread_count']

    @staticmethod
    def get_has_unread_conversations_or_threads(data):
        return data['conversations']['has_unread_conversations_or_threads']

    @staticmethod
    def get_groups(data):
        conversations = data.get('conversations')
        applications = data.get('applications')
        feedback_possible = data.get('feedback_possible')
        groups = defaultdict(dict)
        for group_id, conversation_data in conversations['groups'].items():
            groups[group_id] = {
                **conversation_data,
            }

        for group_id, application_count in applications:
            groups[group_id]['pending_application_count'] = application_count

        for group_id, feedback_possible_count in feedback_possible:
            groups[group_id]['feedback_possible_count'] = feedback_possible_count

        return groups

    @staticmethod
    def get_places(data):
        conversations = data.get('conversations')
        places = {}
        for place_id, conversation_data in conversations['places'].items():
            places[place_id] = {
                **conversation_data,
            }
        return places


def status_data(user):
    return {
        'conversations': unread_conversations(user),
        'applications': pending_applications(user),
        'feedback_possible': get_feedback_possible(user),
        'unseen_notification_count': unseen_notification_count(user),
    }
