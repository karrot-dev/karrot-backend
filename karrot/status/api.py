from collections import defaultdict

from rest_framework import views, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from karrot.status.helpers import unseen_notification_count, \
    unread_conversations, pending_applications, get_feedback_possible


class StatusView(views.APIView):
    permission_classes = (IsAuthenticated, )

    @staticmethod
    def get(request, **kwargs):
        conversations = unread_conversations(request.user)
        applications = pending_applications(request.user)
        feedback_possible = get_feedback_possible(request.user)

        groups = defaultdict(dict)
        for group_id, conversation_data in conversations['groups'].items():
            groups[group_id] = {
                **conversation_data,
            }

        for group_id, application_count in applications:
            groups[group_id]['pending_application_count'] = application_count

        for group_id, feedback_possible_count in feedback_possible:
            groups[group_id]['feedback_possible_count'] = feedback_possible_count

        places = {}
        for place_id, conversation_data in conversations['places'].items():
            places[place_id] = {
                **conversation_data,
            }

        data = {
            'unseen_conversation_count': conversations['unseen_conversation_count'],
            'unseen_thread_count': conversations['unseen_thread_count'],
            'has_unread_conversations_or_threads': conversations['has_unread_conversations_or_threads'],
            'unseen_notification_count': unseen_notification_count(request.user),
            'groups': groups,
            'places': places,
        }

        return Response(data=data, status=status.HTTP_200_OK)
