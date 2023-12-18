import hashlib
import logging
import os
from os.path import abspath
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import prefetch_related_objects, F
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from django.utils.cache import get_conditional_response
from django.utils.http import content_disposition_header, quote_etag
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.applications.models import Application
from karrot.applications.serializers import ApplicationSerializer
from karrot.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationMessageReaction,
    ConversationParticipant,
    ConversationMeta,
    ConversationMessageAttachment,
)
from karrot.conversations.serializers import (
    ConversationSerializer,
    ConversationMessageSerializer,
    ConversationMessageReactionSerializer,
    EmojiField,
    ConversationThreadSerializer,
    ConversationMetaSerializer,
    ConversationMessageAttachmentSerializer,
)
from karrot.issues.models import Issue
from karrot.issues.serializers import IssueSerializer
from karrot.utils.parsers import JSONWithFilesMultiPartParser
from karrot.offers.models import Offer
from karrot.offers.serializers import OfferSerializer
from karrot.activities.models import Activity
from karrot.activities.serializers import ActivitySerializer
from karrot.users.serializers import UserInfoSerializer
from karrot.utils.mixins import PartialUpdateModelMixin

logger = logging.getLogger(__name__)


class ConversationPagination(CursorPagination):
    # It stops us from using conversation__latest_message_id, so we annotate the value with a different name,
    # knowing that the order is not stable
    page_size = 10
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-conversation_latest_message_id"


class ThreadPagination(CursorPagination):
    page_size = 10
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-latest_message_id"


class NewestFirstMessagePagination(CursorPagination):
    page_size = 10
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-id"


class OldestFirstMessagePagination(CursorPagination):
    page_size = 10
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "id"


class CanAccessConversation(BasePermission):
    message = _("You are not in this conversation")

    def has_object_permission(self, request, view, message):
        return message.conversation.can_access(request.user)


class IsAuthorConversationMessage(BasePermission):
    """Is the user the author of the message they wish to update?"""

    message = _("You are not the author of this message")

    def has_object_permission(self, request, view, message):
        if view.action != "partial_update":
            return True
        return request.user == message.author


class IsWithinUpdatePeriod(BasePermission):
    message = _("You can't edit a message more than %(days_number)s days after its creation.") % {
        "days_number": settings.MESSAGE_EDIT_DAYS
    }

    def has_object_permission(self, request, view, message):
        if view.action != "partial_update":
            return True
        return message.is_recent()


class ConversationFilter(filters.FilterSet):
    exclude_read = filters.BooleanFilter(field_name="unread_message_count", method="filter_exclude_read")

    def filter_exclude_read(self, qs, name, value):
        if value is True:
            return qs.exclude(unread_message_count=0)
        return qs

    class Meta:
        model = ConversationParticipant
        fields = ["exclude_read"]


class AttachmentViewSet(mixins.RetrieveModelMixin, GenericViewSet):
    queryset = ConversationMessageAttachment.objects
    serializer_class = ConversationMessageAttachmentSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.with_conversation_access(self.request.user).distinct()

    @action(detail=True, methods=["GET"])
    def preview(self, request, pk=None):
        return send_attachment(request, self.get_object(), preview=True)

    @action(detail=True, methods=["GET"])
    def thumbnail(self, request, pk=None):
        return send_attachment(request, self.get_object(), thumbnail=True)

    @action(detail=True, methods=["GET"])
    def original(self, request, pk=None):
        return send_attachment(request, self.get_object())

    @action(detail=True, methods=["GET"])
    def download(self, request, pk=None):
        return send_attachment(request, self.get_object(), download=True)


class ConversationViewSet(mixins.RetrieveModelMixin, PartialUpdateModelMixin, GenericViewSet):
    """
    Conversations
    """

    # It's more convenient to get participants first, because they relate directly to the request user
    queryset = ConversationParticipant.objects
    lookup_field = "conversation_id"
    lookup_url_kwarg = "pk"
    serializer_class = ConversationSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = ConversationPagination
    filterset_class = ConversationFilter
    filter_backends = (filters.DjangoFilterBackend,)

    def get_queryset(self):
        qs = self.queryset.filter(user=self.request.user)
        if self.action == "retrieve":
            qs = qs.select_related("conversation", "conversation__target_type").annotate_unread_message_count()
        return qs

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            # user is not participant, create mock participant that could be saved if needed
            queryset = Conversation.objects.filter(group__groupmembership__user=self.request.user, group__isnull=False)
            pk = self.kwargs["pk"]
            conversation = get_object_or_404(queryset, id=pk)
            return conversation.make_participant(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = (
            self.get_queryset()
            .exclude(conversation__latest_message_id=None)
            .annotate_unread_message_count()
            .annotate(conversation_latest_message_id=F("conversation__latest_message_id"))
            .select_related(
                "conversation",
                "conversation__latest_message",
                "conversation__target_type",
            )
            .prefetch_related(
                "conversation__latest_message__reactions",
                "conversation__latest_message__images",
                "conversation__latest_message__attachments",
                "conversation__participants",
            )
            .order_by("-conversation__latest_message_id")
        )
        queryset = self.filter_queryset(queryset)

        participations = self.paginate_queryset(queryset)
        conversations = [p.conversation for p in participations]

        messages = [c.latest_message for c in conversations if c.latest_message is not None]

        # Prefetch related objects per target type
        activity_ct = ContentType.objects.get_for_model(Activity)
        activity_conversations = [item for item in conversations if item.target_type == activity_ct]
        activities = (
            Activity.objects.filter(id__in=[c.target_id for c in activity_conversations])
            .select_related("activity_type")
            .prefetch_related(
                "activityparticipant_set",
                "feedback_given_by",
                "activityparticipant_set__participant_type",
                "participant_types",
            )
        )

        applications_ct = ContentType.objects.get_for_model(Application)
        application_conversations = [item for item in conversations if item.target_type == applications_ct]
        applications = Application.objects.filter(
            id__in=[c.target_id for c in application_conversations]
        ).select_related("user")

        issues_ct = ContentType.objects.get_for_model(Issue)
        issue_conversations = [item for item in conversations if item.target_type == issues_ct]
        issues = Issue.objects.filter(id__in=[c.target_id for c in issue_conversations]).prefetch_for_serializer(
            user=request.user
        )

        offers_ct = ContentType.objects.get_for_model(Offer)
        offer_conversations = [item for item in conversations if item.target_type == offers_ct]
        offers = Offer.objects.filter(id__in=[c.target_id for c in offer_conversations]).prefetch_related("images")

        # Applicant does not have access to group member profiles, so we attach reduced user profiles
        my_applications = [a for a in applications if a.user == request.user]

        def get_conversation(application):
            return next(c for c in application_conversations if c.target_id == application.id)

        users = (
            get_user_model()
            .objects.filter(conversationparticipant__conversation__in=[get_conversation(a) for a in my_applications])
            .exclude(id=request.user.id)
        )

        context = self.get_serializer_context()
        serializer = self.get_serializer(participations, many=True)
        message_serializer = ConversationMessageSerializer(messages, many=True, context=context)
        activities_serializer = ActivitySerializer(activities, many=True, context=context)
        application_serializer = ApplicationSerializer(applications, many=True, context=context)
        issue_serializer = IssueSerializer(issues, many=True, context=context)
        offer_serializer = OfferSerializer(offers, many=True, context=context)
        user_serializer = UserInfoSerializer(users, many=True, context=context)
        meta = ConversationMeta.objects.get(user=request.user)
        meta_serializer = ConversationMetaSerializer(meta, context=self.get_serializer_context())

        return self.get_paginated_response(
            {
                "conversations": serializer.data,
                "messages": message_serializer.data,
                "activities": activities_serializer.data,
                "applications": application_serializer.data,
                "issues": issue_serializer.data,
                "offers": offer_serializer.data,
                "users_info": user_serializer.data,
                "meta": meta_serializer.data,
            }
        )

    @action(detail=False, methods=["POST"])
    def mark_conversations_seen(self, request):
        """Trigger this endpoint to mark when the user has seen notifications about new messages in conversations"""
        self.check_permissions(request)
        meta, _ = ConversationMeta.objects.update_or_create(
            {"conversations_marked_at": timezone.now()}, user=request.user
        )
        serializer = ConversationMetaSerializer(meta)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def mark_threads_seen(self, request):
        """Trigger this endpoint to mark when the user has seen notifications about new messages in threads"""
        self.check_permissions(request)
        meta, _ = ConversationMeta.objects.update_or_create({"threads_marked_at": timezone.now()}, user=request.user)
        serializer = ConversationMetaSerializer(meta)
        return Response(serializer.data)


def message_conversation_queryset(request):
    """If the user asks to filter messages by conversation, trigger 'invalid_choice' in the FilterSet"""
    if request is None:
        return Conversation.objects.none()

    return Conversation.objects.with_access(request.user)


class ConversationMessageFilter(filters.FilterSet):
    conversation = filters.ModelChoiceFilter(
        queryset=message_conversation_queryset, error_messages={"invalid_choice": _("You are not in this conversation")}
    )

    exclude_read = filters.BooleanFilter(field_name="unread_replies_count", method="filter_exclude_read")

    def filter_exclude_read(self, qs, name, value):
        if value is True:
            return qs.exclude(unread_replies_count=0)
        return qs

    class Meta:
        model = ConversationMessage
        fields = ("conversation", "thread", "exclude_read")


class ConversationMessageViewSet(
    mixins.CreateModelMixin,
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
        CanAccessConversation,
        IsAuthorConversationMessage,
        IsWithinUpdatePeriod,
    )
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ConversationMessageFilter
    pagination_class = NewestFirstMessagePagination
    parser_classes = [JSONWithFilesMultiPartParser, JSONParser]

    @property
    def paginator(self):
        # optional 'order' query param to explicitly set the ordering
        order = self.request.query_params.get("order", None)
        if order == "newest-first":
            self.pagination_class = NewestFirstMessagePagination
        elif order == "oldest-first":
            self.pagination_class = OldestFirstMessagePagination
        # otherwise do what it did before the 'order' parameter existed
        elif self.request.query_params.get("thread", None):
            self.pagination_class = OldestFirstMessagePagination
        return super().paginator

    def get_queryset(self):
        if self.action in ("partial_update", "thread"):
            return self.queryset
        return self.queryset.with_conversation_access(self.request.user).distinct()

    def list(self, request, *args, **kwargs):
        # Workaround to avoid extremely slow cases
        # https://github.com/karrot-dev/karrot-frontend/issues/2369
        # Split up query in two parts:
        # 1. get message ids, including costly access control
        queryset = ConversationMessage.objects.with_conversation_access(request.user).values("id").distinct()
        if self.request.query_params.get("thread", None):
            queryset = queryset.only_threads_and_replies()
        else:
            queryset = queryset.exclude_replies()
        queryset = self.filter_queryset(queryset)
        message_ids = [m["id"] for m in self.paginate_queryset(queryset)]

        # 2. get data, including costly annotations
        messages = (
            ConversationMessage.objects.filter(id__in=message_ids)
            .annotate_replies_count()
            .annotate_unread_replies_count_for(request.user)
            .order_by(self.pagination_class.ordering)
            .prefetch_related("reactions", "participants", "images", "attachments")
        )

        serializer = self.get_serializer(messages, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Lists threads the user has participated in",
        parameters=[
            OpenApiParameter("group", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("conversation", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("exclude_read", OpenApiTypes.BOOL, OpenApiParameter.QUERY),
        ],
    )
    @action(
        detail=False,
    )
    def my_threads(self, request):
        queryset = (
            ConversationMessage.objects.distinct()
            .only_threads_with_user(self.request.user)
            .annotate_replies_count()
            .annotate_unread_replies_count_for(request.user)
            .prefetch_related("participants", "latest_message")
        )
        queryset = self.filter_queryset(queryset)
        paginator = ThreadPagination()

        threads = list(paginator.paginate_queryset(queryset, request, view=self))
        messages = [t.latest_message for t in threads if t.latest_message is not None]

        prefetch_related_objects(threads + messages, "reactions")
        prefetch_related_objects(threads + messages, "images")
        prefetch_related_objects(threads + messages, "attachments")

        serializer = self.get_serializer(threads, many=True)
        message_serializer = self.get_serializer(messages, many=True)
        return paginator.get_paginated_response({"threads": serializer.data, "messages": message_serializer.data})

    def partial_update(self, request, *args, **kwargs):
        """Update one of your messages"""
        return super().partial_update(request)

    @action(detail=True, methods=["PATCH"], serializer_class=ConversationThreadSerializer)
    def thread(self, request, pk=None):
        message = self.get_object()
        if not message.is_first_in_thread():
            raise ValidationError(_("Must be first in thread"))
        participant = message.participants.filter(user=request.user).first()
        if not participant:
            raise ValidationError(_("You are not a participant in this thread"))
        serializer = self.get_serializer(participant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(
        detail=True,
        methods=("POST",),
    )
    def reactions(self, request, pk):
        """route for POST /messages/{id}/reactions/ with body {"name":"emoji_name"}"""

        message = get_object_or_404(ConversationMessage, id=pk)
        self.check_object_permissions(self.request, message)

        data = {
            "message": pk,
            "name": request.data.get("name"),
            "user": request.user.id,
        }

        serializer = ConversationMessageReactionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[OpenApiParameter("name", OpenApiTypes.STR, OpenApiParameter.PATH)])
    @action(
        detail=True,
        methods=("DELETE",),
        url_path="reactions/(?P<name>[a-z0-9_+-]+)",
        url_name="remove_reaction",
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
        group = message.conversation.group
        if group:
            group.refresh_active_status()


class RetrieveConversationMixin(object):
    """Retrieve a conversation instance."""

    def retrieve_conversation(self, request, *args, **kwargs):
        target = self.get_object()
        conversation = (
            Conversation.objects.prefetch_related("conversationparticipant_set")
            .select_related("target_type")
            .get_or_create_for_target(target)
        )

        participant = conversation.conversationparticipant_set.filter(user=request.user).first()
        if not participant:
            if conversation.can_access(request.user):
                participant = conversation.make_participant()
            else:
                self.permission_denied(request, message=_("You are not in this conversation"))

        serializer = ConversationSerializer(participant, context=self.get_serializer_context())
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
        serializer = ConversationSerializer(participant, context=self.get_serializer_context())
        return Response(serializer.data)


def send_attachment(request, attachment, download=False, thumbnail=False, preview=False):
    file, filename, content_type = get_attachment_info(attachment, thumbnail, preview)

    if not file:
        return Http404()

    if settings.FILE_UPLOAD_USE_ACCEL_REDIRECT:
        return AttachmentAccelRedirectResponse(file, filename, content_type, download)

    etag = quote_etag(file_digest(file))  # could save this in the db to not calculate it each time

    response = get_conditional_response(
        request,
        etag=etag,
    )
    if response is None:
        response = AttachmentResponse(file, filename, content_type, download)

    if request.method in ("GET", "HEAD"):
        if etag:
            response.headers.setdefault("ETag", etag)

    return response


class AttachmentResponse(FileResponse):
    """An HTTP response to serve an attachment"""

    def __init__(self, file, filename, content_type, download):
        super().__init__(
            open(file.path, "rb"),
            as_attachment=download,
            filename=filename,
            headers={
                "Content-Type": content_type,
            },
        )


class AttachmentAccelRedirectResponse(HttpResponse):
    """Sends an attachment as an nginx X-Accel-Redirect thing"""

    def __init__(self, file, filename, content_type, download):
        super().__init__()
        attachment_path = abspath(str(file.path))
        media_root = abspath(settings.MEDIA_ROOT)
        if not attachment_path.startswith(media_root):
            raise ValueError("path is not within media root :/")
        accel_redirect_location = "/uploads"  # this is what you set as nginx location
        accel_redirect_path = os.path.join(accel_redirect_location, attachment_path[len(media_root) + 1 :])
        self.headers["Content-Type"] = content_type
        self.headers["Content-Disposition"] = content_disposition_header(download, filename)
        self.headers["X-Accel-Redirect"] = quote(accel_redirect_path)


def get_attachment_info(attachment, thumbnail=False, preview=False):
    """Gets attachment info"""
    file = attachment.file
    filename = attachment.filename
    content_type = attachment.content_type
    if thumbnail:
        file = attachment.thumbnail
        filename = "thumbnail.jpg"
        content_type = "image/jpeg"
    elif preview:
        file = attachment.preview
        filename = "preview.jpg"
        content_type = "image/jpeg"
    return file, filename, content_type


def file_digest(file):
    sha256_hash = hashlib.sha256()
    # Read and update hash string value in blocks of 4K
    for byte_block in iter(lambda: file.read(4096), b""):
        sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
