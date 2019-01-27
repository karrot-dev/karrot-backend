import coreapi
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import prefetch_related_objects, F
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.schemas import ManualSchema
from rest_framework.viewsets import GenericViewSet

from foodsaving.applications.models import Application
from foodsaving.applications.serializers import ApplicationSerializer
from foodsaving.conversations.models import (
    Conversation, ConversationMessage, ConversationMessageReaction, ConversationParticipant, ConversationMeta
)
from foodsaving.conversations.serializers import (
    ConversationSerializer, ConversationMessageSerializer, ConversationMessageReactionSerializer, EmojiField,
    ConversationThreadSerializer, ConversationMetaSerializer
)
from foodsaving.issues.models import Issue
from foodsaving.issues.serializers import IssueSerializer
from foodsaving.pickups.models import PickupDate
from foodsaving.pickups.serializers import PickupDateSerializer
from foodsaving.users.serializers import UserInfoSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class SearchViewSet(GenericViewSet):
    """
    Search
    """

    permission_classes = (IsAuthenticated, )
    schema = ManualSchema(
        description='Search through Karrot', fields=[
            coreapi.Field('q', location='query'),
        ]
    )

    def list(self, request, *args, **kwargs):
        term = request.query_params.get('q')

        vector = SearchVector('content')
        query = SearchQuery(term)
        rank = SearchRank(vector, query)

        messages = ConversationMessage.objects \
                       .filter(conversation__conversationparticipant__user=request.user)\
                       .annotate(rank=rank)\
                       .order_by('-rank')\
                       .filter(rank__gt=0)[:20]

        conversations = [m.conversation for m in messages]
        participations = ConversationParticipant.objects.filter(user=request.user, conversation__in=conversations)

        # Prefetch related objects per target type
        pickup_ct = ContentType.objects.get_for_model(PickupDate)
        pickup_conversations = [item for item in conversations if item.target_type == pickup_ct]
        pickups = PickupDate.objects. \
            filter(id__in=[c.target_id for c in pickup_conversations]). \
            prefetch_related('pickupdatecollector_set', 'feedback_given_by')

        applications_ct = ContentType.objects.get_for_model(Application)
        application_conversations = [item for item in conversations if item.target_type == applications_ct]
        applications = Application.objects. \
            filter(id__in=[c.target_id for c in application_conversations]). \
            select_related('user')

        issues_ct = ContentType.objects.get_for_model(Issue)
        issue_conversations = [item for item in conversations if item.target_type == issues_ct]
        issues = Issue.objects. \
            filter(id__in=[c.target_id for c in issue_conversations]). \
            prefetch_for_serializer(user=request.user)

        # Applicant does not have access to group member profiles, so we attach reduced user profiles
        my_applications = [a for a in applications if a.user == request.user]

        def get_conversation(application):
            return next(c for c in application_conversations if c.target_id == application.id)

        users = get_user_model().objects. \
            filter(conversationparticipant__conversation__in=[get_conversation(a) for a in my_applications]). \
            exclude(id=request.user.id)

        context = self.get_serializer_context()
        conversation_serializer = ConversationSerializer(participations, many=True, context=context)
        message_serializer = ConversationMessageSerializer(messages, many=True, context=context)
        pickups_serializer = PickupDateSerializer(pickups, many=True, context=context)
        application_serializer = ApplicationSerializer(applications, many=True, context=context)
        issue_serializer = IssueSerializer(issues, many=True, context=context)
        user_serializer = UserInfoSerializer(users, many=True, context=context)

        return Response({
            'conversations': conversation_serializer.data,
            'messages': message_serializer.data,
            'pickups': pickups_serializer.data,
            'applications': application_serializer.data,
            'issues': issue_serializer.data,
            'users_info': user_serializer.data,
        })
