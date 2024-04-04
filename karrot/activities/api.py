from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.authentication import BaseAuthentication, BasicAuthentication, SessionAuthentication
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.activities.filters import (
    ActivitiesFilter,
    ActivitySeriesFilter,
    ActivityTypeFilter,
    FeedbackFilter,
    PublicActivitiesFilter,
)
from karrot.activities.models import (
    Activity as ActivityModel,
)
from karrot.activities.models import (
    ActivitySeries as ActivitySeriesModel,
)
from karrot.activities.models import (
    ActivityType,
    ICSAuthToken,
)
from karrot.activities.models import (
    Feedback as FeedbackModel,
)
from karrot.activities.permissions import (
    CannotChangeGroup,
    HasJoinedActivity,
    HasNotJoinedActivity,
    IsEmptyActivity,
    IsGroupEditor,
    IsNotPast,
    IsNotUpcoming,
    IsRecentActivity,
    IsSameParticipant,
    IsUpcoming,
    TypeHasNoActivities,
)
from karrot.activities.renderers import ICSCalendarRenderer
from karrot.activities.serializers import (
    ActivityDismissFeedbackSerializer,
    ActivityICSSerializer,
    ActivityJoinSerializer,
    ActivityLeaveSerializer,
    ActivitySerializer,
    ActivitySeriesHistorySerializer,
    ActivitySeriesSerializer,
    ActivitySeriesUpdateCheckSerializer,
    ActivitySeriesUpdateSerializer,
    ActivityTypeSerializer,
    ActivityUpdateCheckSerializer,
    ActivityUpdateSerializer,
    FeedbackExportRenderer,
    FeedbackExportSerializer,
    FeedbackSerializer,
    PublicActivityICSSerializer,
    PublicActivitySerializer,
)
from karrot.conversations.api import RetrieveConversationMixin
from karrot.history.models import History, HistoryTypus
from karrot.utils.mixins import PartialUpdateModelMixin
from karrot.utils.parsers import JSONWithFilesMultiPartParser


class ICSQueryTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.query_params.get("token", None)
        if not token:
            return None
        try:
            token = ICSAuthToken.objects.select_related("user").get(token=token)
        except ICSAuthToken.DoesNotExist:
            return None
        except ValidationError:
            return None
        user = token.user
        return user, None


class ActivityTypeViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ActivityTypeSerializer
    queryset = ActivityType.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ActivityTypeFilter
    permission_classes = (
        IsAuthenticated,
        IsGroupEditor,
        TypeHasNoActivities,
        CannotChangeGroup,
    )

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)


class FeedbackPagination(CursorPagination):
    page_size = 10
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-activity_date"


class FeedbackViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    GenericViewSet,
):
    """
    Feedback

    # Query parameters
    - `?given_by` - filter by user id
    - `?about` - filter by activity id
    - `?place` - filter by place id
    - `?group` - filter by group id
    - `?created_at_before` and `?created_at_after` - filter by creation date

    export:
    Export Feedback as CSV
    """

    serializer_class = FeedbackSerializer
    queryset = FeedbackModel.objects.all()
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = FeedbackFilter
    permission_classes = (IsAuthenticated, IsSameParticipant, IsRecentActivity)
    pagination_class = FeedbackPagination

    def get_queryset(self):
        return self.queryset.filter(about__place__group__members=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = (
            self.filter_queryset(self.get_queryset())
            .select_related("about")
            .prefetch_related(
                "about__activity_type",
                "about__activityparticipant_set",
                "about__feedback_given_by",
                "about__participant_types",
                "about__activityparticipant_set__participant_type",
                "no_shows",
            )
            .annotate(timezone=F("about__place__group__timezone"), activity_date=F("about__date__startswith"))
        )

        feedback = self.paginate_queryset(queryset)

        activities = set()
        for f in feedback:
            activity = f.about
            activity.timezone = f.timezone
            activities.add(activity)

        serializer = self.get_serializer(feedback, many=True)
        context = self.get_serializer_context()
        activities_serializer = ActivitySerializer(activities, many=True, context=context)
        return self.get_paginated_response(
            {
                "feedback": serializer.data,
                "activities": activities_serializer.data,
            }
        )

    @action(
        detail=False,
        methods=["GET"],
        renderer_classes=(FeedbackExportRenderer,),
        pagination_class=None,
        serializer_class=FeedbackExportSerializer,
    )
    def export(self, request, format=None):
        queryset = (
            self.filter_queryset(self.get_queryset())
            .select_related("about", "about__place", "about__place__group")
            .order_by("-about__date")
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ActivitySeriesViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ActivitySeriesSerializer
    queryset = ActivitySeriesModel.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ActivitySeriesFilter
    permission_classes = (IsAuthenticated, IsGroupEditor)
    parser_classes = [JSONWithFilesMultiPartParser, JSONParser]

    def get_queryset(self):
        return self.queryset.filter(place__group__members=self.request.user)

    def get_serializer_class(self):
        if self.action == "partial_update":
            return ActivitySeriesUpdateSerializer
        return self.serializer_class

    def perform_destroy(self, series):
        data = self.get_serializer(series).data
        History.objects.create(
            typus=HistoryTypus.SERIES_DELETE,
            group=series.place.group,
            place=series.place,
            users=[
                self.request.user,
            ],
            payload=data,
            before=ActivitySeriesHistorySerializer(series).data,
        )
        super().perform_destroy(series)
        series.place.group.refresh_active_status()

    @action(
        detail=True,
        methods=["PATCH"],
        permission_classes=(IsAuthenticated,),
        serializer_class=ActivitySeriesUpdateCheckSerializer,
    )
    def check(self, request, pk):
        self.check_permissions(request)
        instance = self.get_object()
        self.check_object_permissions(request, instance)
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data)


class ActivityPagination(CursorPagination):
    page_size = 30
    max_page_size = 1200
    page_size_query_param = "page_size"


class PublicActivityViewSet(
    GenericViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    serializer_class = PublicActivitySerializer
    queryset = ActivityModel.objects.is_public().exclude_disabled().filter(place__archived_at__isnull=True)
    filter_backends = (
        filters.DjangoFilterBackend,
        OrderingFilter,
    )
    filterset_class = PublicActivitiesFilter
    pagination_class = ActivityPagination  # use the activities one seems ok
    ordering_fields = ["date"]
    ordering = ["date"]

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, public_id=self.kwargs["pk"])
        return obj

    @extend_schema(responses=OpenApiTypes.STR)
    @action(
        detail=True,
        methods=["GET"],
        renderer_classes=(ICSCalendarRenderer,),
        serializer_class=PublicActivityICSSerializer,
        url_path="ics",
    )
    def ics_detail(self, request, pk=None):
        response = self.retrieve(request)
        filename = f"activity-{pk}.ics"
        response["content-disposition"] = f"attachment; filename={filename}"
        return response

    @extend_schema(operation_id="public_activities_ics_list", responses=OpenApiTypes.STR)
    @action(
        detail=False,
        methods=["GET"],
        renderer_classes=(ICSCalendarRenderer,),
        serializer_class=PublicActivityICSSerializer,
        url_path="ics",
        pagination_class=None,
    )
    def ics_list(self, request):
        response = self.list(request)
        filename = "activities.ics"
        response["content-disposition"] = f"attachment; filename={filename}"
        return response


class ActivityViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
    RetrieveConversationMixin,
):
    """
    Activities
    """

    serializer_class = ActivitySerializer
    queryset = ActivityModel.objects
    filter_backends = (
        filters.DjangoFilterBackend,
        OrderingFilter,
    )
    filterset_class = ActivitiesFilter
    permission_classes = (IsAuthenticated, IsUpcoming, IsGroupEditor, IsEmptyActivity)
    pagination_class = ActivityPagination
    parser_classes = [JSONWithFilesMultiPartParser, JSONParser]
    ordering_fields = ["date"]
    ordering = ["date"]

    def get_queryset(self):
        qs = self.queryset.filter(place__group__members=self.request.user)
        if self.action in ("list", "ics_list"):
            # TODO: need to decide how to ensure we fetch all activities for feedback page, even if place archived
            # only filter list by not archived places, as we need still need to retrieve activities for archived places
            qs = qs.filter(place__archived_at__isnull=True)
        if self.action in ("retrieve", "list"):
            # because we have participants field in the serializer
            # only prefetch on read_only actions, otherwise there are caching problems when participants get added
            qs = qs.select_related(
                "activity_type",
                "series",
            ).prefetch_related(
                "activityparticipant_set",
                "feedback_set",
                "participant_types",
                "activityparticipant_set__participant_type",
                "feedback_set__no_shows",
            )
        if self.action in ("ics_detail", "ics_list"):
            qs = qs.select_related(
                "activity_type",
                "place",
            ).prefetch_related(
                "participant_types",
                "participants",
            )

        if self.action == "add":
            # Lock activity when adding a participant
            # This should prevent a race condition that would result in more participants than slots
            qs = qs.select_for_update()
        return qs

    def get_serializer_class(self):
        if self.action == "partial_update":
            return ActivityUpdateSerializer
        return self.serializer_class

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, IsNotPast, HasNotJoinedActivity),
        serializer_class=ActivityJoinSerializer,
    )
    def add(self, request, pk=None):
        # Transaction needed by select_for_update
        with transaction.atomic():
            return self.partial_update(request)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, IsNotPast, HasJoinedActivity),
        serializer_class=ActivityLeaveSerializer,
    )
    def remove(self, request, pk=None):
        return self.partial_update(request)

    @action(
        detail=True,
        methods=["PATCH"],
        permission_classes=(IsAuthenticated,),
        serializer_class=ActivityUpdateCheckSerializer,
    )
    def check(self, request, pk):
        self.check_permissions(request)
        instance = self.get_object()
        self.check_object_permissions(request, instance)
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this activity"""
        return self.retrieve_conversation(request, pk)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, HasJoinedActivity, IsNotUpcoming),
        serializer_class=ActivityDismissFeedbackSerializer,
    )
    def dismiss_feedback(self, request, pk=None):
        return self.partial_update(request)

    @extend_schema(responses=OpenApiTypes.STR)
    @action(
        detail=True,
        methods=["GET"],
        renderer_classes=(ICSCalendarRenderer,),
        serializer_class=ActivityICSSerializer,
        url_path="ics",
    )
    def ics_detail(self, request, pk=None):
        response = self.retrieve(request)
        filename = f"activity-{pk}.ics"
        response["content-disposition"] = f"attachment; filename={filename}"
        return response

    @extend_schema(operation_id="activities_ics_list", responses=OpenApiTypes.STR)
    @action(
        detail=False,
        methods=["GET"],
        renderer_classes=(ICSCalendarRenderer,),
        serializer_class=ActivityICSSerializer,
        url_path="ics",
        authentication_classes=[BasicAuthentication, SessionAuthentication, ICSQueryTokenAuthentication],
        pagination_class=None,
    )
    def ics_list(self, request):
        response = self.list(request)
        filename = "activities.ics"
        response["content-disposition"] = f"attachment; filename={filename}"
        return response

    @extend_schema(responses=OpenApiTypes.STR)
    @action(detail=False, methods=["GET"], pagination_class=None)
    def ics_token(self, request):
        user = request.user
        try:
            token = ICSAuthToken.objects.get(user=user).token
        except ICSAuthToken.DoesNotExist:
            return self.ics_token_refresh(request)
        return Response(token)

    @extend_schema(request=None, responses=OpenApiTypes.STR)
    @action(detail=False, methods=["POST"], pagination_class=None)
    def ics_token_refresh(self, request):
        user = request.user
        ICSAuthToken.objects.filter(user=user).delete()
        token = ICSAuthToken.objects.create(user=user).token
        return Response(token)
