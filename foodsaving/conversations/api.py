import coreapi
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import prefetch_related_objects, F
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

from foodsaving.applications.models import GroupApplication
from foodsaving.applications.serializers import GroupApplicationSerializer
from foodsaving.issues.models import Issue
from foodsaving.issues.serializers import IssueSerializer
from foodsaving.conversations.models import (
    Conversation, ConversationMessage, ConversationMessageReaction, ConversationParticipant
)
from foodsaving.conversations.serializers import (
    ConversationSerializer, ConversationMessageSerializer, ConversationMessageReactionSerializer, EmojiField,
    ConversationThreadSerializer
)
from foodsaving.pickups.models import PickupDate
from foodsaving.pickups.serializers import PickupDateSerializer
from foodsaving.users.serializers import UserInfoSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class ConversationPagination(CursorPagination):
    # It stops us from using conversation__latest_message_id, so we annotate the value with a different name,
    # knowing that the order is not stable
    page_size = 10
    ordering = '-conversation_latest_message_id'


class ThreadPagination(CursorPagination):
    page_size = 10
    ordering = '-latest_message_id'


class MessagePagination(CursorPagination):
    # TODO: create an index on 'created_at' for increased speed
    page_size = 10
    ordering = '-created_at'


class ReverseMessagePagination(CursorPagination):
    page_size = 10
    ordering = 'created_at'


class IsConversationParticipant(BasePermission):
    message = _('You are not in this conversation')

    def has_permission(self, request, view):
        """If the user asks to filter messages by conversation, return an error if
        they are not part of the conversation (instead of returning empty result)
        """
        conversation_id = request.GET.get('conversation', None)

        # if they specify a conversation, check they are in it
        if conversation_id:
            return ConversationParticipant.objects.filter(conversation=conversation_id, user=request.user).exists()

        # otherwise it is fine (messages will be filtered for the users conversations)
        return True

    def has_object_permission(self, request, view, message):
        return message.conversation.participants.filter(id=request.user.id).exists()


class IsAuthorConversationMessage(BasePermission):
    """Is the user the author of the message they wish to update?"""

    message = _('You are not the author of this message')

    def has_object_permission(self, request, view, message):
        if view.action != 'partial_update':
            return True
        return request.user == message.author


class IsWithinUpdatePeriod(BasePermission):
    message = _('You can\'t edit a message more than %(days_number)s days after its creation.') % \
        {'days_number': settings.MESSAGE_EDIT_DAYS}

    def has_object_permission(self, request, view, message):
        if view.action != 'partial_update':
            return True
        return message.is_recent()


class ConversationFilter(filters.FilterSet):
    exclude_read = filters.BooleanFilter(field_name='unread_message_count', method='filter_exclude_read')

    def filter_exclude_read(self, qs, name, value):
        if value is True:
            return qs.exclude(unread_message_count=0)
        return qs

    class Meta:
        model = ConversationParticipant
        fields = ['exclude_read']


class ConversationViewSet(mixins.RetrieveModelMixin, PartialUpdateModelMixin, GenericViewSet):
    """
    Conversations
    """

    # It's more convenient to get participants first, because they relate directly to the request user
    queryset = ConversationParticipant.objects
    lookup_field = 'conversation_id'
    lookup_url_kwarg = 'pk'
    serializer_class = ConversationSerializer
    permission_classes = (IsAuthenticated, )
    pagination_class = ConversationPagination
    filterset_class = ConversationFilter
    filter_backends = (filters.DjangoFilterBackend, )

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset() \
            .exclude(conversation__latest_message_id=None) \
            .annotate_unread_message_count() \
            .annotate(conversation_latest_message_id=F('conversation__latest_message_id')) \
            .select_related(
                'conversation',
                'conversation__latest_message',
                'conversation__target_type',
             ) \
            .prefetch_related(
                'conversation__latest_message__reactions',
                'conversation__participants',
             ) \
            .order_by('-conversation__latest_message_id')
        queryset = self.filter_queryset(queryset)

        participations = self.paginate_queryset(queryset)
        conversations = [p.conversation for p in participations]

        messages = [c.latest_message for c in conversations if c.latest_message is not None]

        # Prefetch related objects per target type
        pickup_ct = ContentType.objects.get_for_model(PickupDate)
        pickup_conversations = [item for item in conversations if item.target_type == pickup_ct]
        pickups = PickupDate.objects. \
            filter(id__in=[c.target_id for c in pickup_conversations]). \
            prefetch_related('pickupdatecollector_set', 'feedback_given_by')

        applications_ct = ContentType.objects.get_for_model(GroupApplication)
        application_conversations = [item for item in conversations if item.target_type == applications_ct]
        applications = GroupApplication.objects. \
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
        serializer = self.get_serializer(participations, many=True)
        message_serializer = ConversationMessageSerializer(messages, many=True, context=context)
        pickups_serializer = PickupDateSerializer(pickups, many=True, context=context)
        application_serializer = GroupApplicationSerializer(applications, many=True, context=context)
        issue_serializer = IssueSerializer(issues, many=True, context=context)
        user_serializer = UserInfoSerializer(users, many=True, context=context)

        return self.get_paginated_response({
            'conversations': serializer.data,
            'messages': message_serializer.data,
            'pickups': pickups_serializer.data,
            'applications': application_serializer.data,
            'issues': issue_serializer.data,
            'users_info': user_serializer.data,
        })


class ConversationMessageFilter(filters.FilterSet):
    exclude_read = filters.BooleanFilter(field_name='unread_replies_count', method='filter_exclude_read')

    def filter_exclude_read(self, qs, name, value):
        if value is True:
            return qs.exclude(unread_replies_count=0)
        return qs

    class Meta:
        model = ConversationMessage
        fields = ('conversation', 'thread', 'exclude_read')


class ConversationMessageViewSet(
        mixins.CreateModelMixin,
        mixins.ListModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        GenericViewSet,
):
    """
    ConversationMessages
    """

    queryset = ConversationMessage.objects
    serializer_class = ConversationMessageSerializer
    permission_classes = (
        IsAuthenticated,
        IsConversationParticipant,
        IsAuthorConversationMessage,
        IsWithinUpdatePeriod,
    )
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = ConversationMessageFilter
    pagination_class = MessagePagination

    @property
    def paginator(self):
        if self.request.query_params.get('thread', None):
            self.pagination_class = ReverseMessagePagination
        return super().paginator

    def get_queryset(self):
        if self.action in ('partial_update', 'thread'):
            return self.queryset
        qs = self.queryset \
            .filter(conversation__participants=self.request.user) \
            .annotate_replies_count() \
            .annotate_unread_replies_count_for(self.request.user)

        if self.action == 'my_threads':
            return qs

        if self.action == 'list':
            qs = qs.prefetch_related('reactions', 'participants')

        if self.request.query_params.get('thread', None):
            return qs.only_threads_and_replies()

        return qs.exclude_replies()

    @action(
        detail=False,
        schema=ManualSchema(
            description='Lists threads the user has participated in',
            fields=[
                coreapi.Field('group', location='query'),
                coreapi.Field('conversation', location='query'),
                coreapi.Field('exclude_read', location='query'),
            ]
        )
    )
    def my_threads(self, request):
        queryset = self.get_queryset() \
            .only_threads_with_user(request.user) \
            .select_related('latest_message') \
            .prefetch_related('participants')
        queryset = self.filter_queryset(queryset)
        paginator = ThreadPagination()

        threads = list(paginator.paginate_queryset(queryset, request, view=self))
        messages = [t.latest_message for t in threads if t.latest_message is not None]

        prefetch_related_objects(threads + messages, 'reactions')

        serializer = self.get_serializer(threads, many=True)
        message_serializer = self.get_serializer(messages, many=True)
        return paginator.get_paginated_response({'threads': serializer.data, 'messages': message_serializer.data})

    def partial_update(self, request, *args, **kwargs):
        """Update one of your messages"""
        return super().partial_update(request)

    @action(detail=True, methods=['PATCH'], serializer_class=ConversationThreadSerializer)
    def thread(self, request, pk=None):
        message = self.get_object()
        if not message.is_first_in_thread():
            raise ValidationError(_('Must be first in thread'))
        participant = message.participants.filter(user=request.user).first()
        if not participant:
            raise ValidationError(_('You are not a participant in this thread'))
        serializer = self.get_serializer(participant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(
        detail=True,
        methods=('POST', ),
    )
    def reactions(self, request, pk):
        """route for POST /messages/{id}/reactions/ with body {"name":"emoji_name"}"""

        message = get_object_or_404(ConversationMessage, id=pk)
        self.check_object_permissions(self.request, message)

        data = {
            'message': pk,
            'name': request.data.get('name'),
            'user': request.user.id,
        }

        serializer = ConversationMessageReactionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=('DELETE', ),
        url_path='reactions/(?P<name>[a-z0-9_+-]+)',
        url_name='remove_reaction',
    )
    def remove_reaction(self, request, pk, name):
        """route for DELETE /messages/{id}/reactions/{name}/"""

        name = EmojiField.to_internal_value(None, name)
        message = get_object_or_404(ConversationMessage, id=pk)

        # object permissions check has to be triggered manually
        self.check_object_permissions(self.request, message)

        reaction = get_object_or_404(ConversationMessageReaction, name=name, message=message, user=request.user)

        reaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        message = serializer.save()
        if message.conversation.type() == 'group':
            group = message.conversation.target
            group.refresh_active_status()


class RetrieveConversationMixin(object):
    """Retrieve a conversation instance."""

    def retrieve_conversation(self, request, *args, **kwargs):
        target = self.get_object()
        conversation = Conversation.objects. \
            prefetch_related('conversationparticipant_set'). \
            select_related('target_type'). \
            get_or_create_for_target(target)
        try:
            participant = conversation.conversationparticipant_set.get(user=request.user)
        except ConversationParticipant.DoesNotExist:
            self.permission_denied(request, message=_('You are not in this conversation'))
        serializer = ConversationSerializer(participant, data={}, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class RetrievePrivateConversationMixin(object):
    """Retrieve a private user conversation instance."""

    def retrieve_private_conversation(self, request, *args, **kwargs):
        user2 = self.get_object()
        try:
            conversation = Conversation.objects.get_or_create_for_two_users(request.user, user2)
        except Exception:
            return Response(status=status.HTTP_404_NOT_FOUND, data={})
        participant = conversation.conversationparticipant_set.get(user=request.user)
        serializer = ConversationSerializer(participant, data={}, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
