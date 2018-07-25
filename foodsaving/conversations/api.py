from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.models import (
    Conversation, ConversationMessage, ConversationMessageReaction, ConversationParticipant
)
from foodsaving.conversations.serializers import (
    ConversationSerializer,
    ConversationMessageSerializer,
    ConversationMessageReactionSerializer,
    ConversationMarkSerializer,
    ConversationEmailNotificationsSerializer,
    EmojiField,
    ConversationThreadSerializer,
)
from foodsaving.groups.models import Group
from foodsaving.utils.mixins import PartialUpdateModelMixin


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


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    Conversations
    """

    queryset = Conversation.objects
    serializer_class = ConversationSerializer
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        return self.queryset.filter(participants=self.request.user)

    @action(detail=True, methods=['POST'], serializer_class=ConversationMarkSerializer)
    def mark(self, request, pk=None):
        conversation = self.get_object()
        participant = conversation.conversationparticipant_set.get(user=request.user)
        serializer = self.get_serializer(participant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['POST'], serializer_class=ConversationEmailNotificationsSerializer)
    def email_notifications(self, request, pk=None):
        conversation = self.get_object()
        participant = conversation.conversationparticipant_set.get(user=request.user)
        serializer = self.get_serializer(participant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ConversationMessageViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                 PartialUpdateModelMixin, GenericViewSet):
    """
    ConversationMessages
    """

    queryset = ConversationMessage.objects \
        .prefetch_related('reactions') \
        .prefetch_related('participants') \
        .annotate_replies_count()

    serializer_class = ConversationMessageSerializer
    permission_classes = (
        IsAuthenticated,
        IsConversationParticipant,
        IsAuthorConversationMessage,
        IsWithinUpdatePeriod,
    )
    filter_backends = (DjangoFilterBackend, )
    filterset_fields = (
        'conversation',
        'thread',
    )
    pagination_class = MessagePagination

    @property
    def paginator(self):
        if self.request.query_params.get('thread', None):
            self.pagination_class = ReverseMessagePagination
        return super().paginator

    def get_queryset(self):
        if self.action == 'partial_update':
            return self.queryset
        qs = self.queryset \
            .filter(conversation__participants=self.request.user) \
            .annotate_unread_replies_count_for(self.request.user)

        if self.request.query_params.get('thread', None):
            return qs.only_threads_and_replies()
        else:
            return qs.exclude_replies()

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
        filterset_fields=('name', ),
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
        if isinstance(message.conversation.target, Group):
            group = message.conversation.target
            group.refresh_active_status()


class RetrieveConversationMixin(object):
    """Retrieve a conversation instance."""

    def retrieve_conversation(self, request, *args, **kwargs):
        target = self.get_object()
        conversation = Conversation.objects.get_or_create_for_target(target)
        serializer = ConversationSerializer(conversation, data={}, context={'request': request})
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
        serializer = ConversationSerializer(conversation, data={}, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
