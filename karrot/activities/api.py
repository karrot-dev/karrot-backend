from django.db.models import F
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrieveConversationMixin
from karrot.history.models import History, HistoryTypus
from karrot.activities.filters import (ActivitiesFilter, ActivitySeriesFilter, FeedbackFilter)
from karrot.activities.models import (
    Activity as ActivityModel, ActivitySeries as ActivitySeriesModel, Feedback as FeedbackModel
)
from karrot.activities.permissions import (
    IsUpcoming, HasNotJoinedActivity, HasJoinedActivity, IsEmptyActivity, IsNotFull, IsSameParticipant,
    IsRecentActivity, IsGroupEditor
)
from karrot.activities.serializers import (
    ActivitySerializer, ActivitySeriesSerializer, ActivityJoinSerializer, ActivityLeaveSerializer, FeedbackSerializer,
    ActivityUpdateSerializer, ActivitySeriesUpdateSerializer, ActivitySeriesHistorySerializer,
    FeedbackExportSerializer, FeedbackExportRenderer
)
from karrot.places.models import PlaceStatus
from karrot.utils.mixins import PartialUpdateModelMixin


class FeedbackPagination(CursorPagination):
    page_size = 10
    ordering = '-activity_date'


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
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = FeedbackFilter
    permission_classes = (IsAuthenticated, IsSameParticipant, IsRecentActivity)
    pagination_class = FeedbackPagination

    def get_queryset(self):
        return self.queryset.filter(about__place__group__members=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()) \
            .select_related('about') \
            .prefetch_related('about__activityparticipant_set', 'about__feedback_given_by') \
            .annotate(
              timezone=F('about__place__group__timezone'),
              activity_date=F('about__date__startswith'))
        feedback = self.paginate_queryset(queryset)

        activities = set()
        for f in feedback:
            activity = f.about
            setattr(activity, 'timezone', f.timezone)
            activities.add(activity)

        serializer = self.get_serializer(feedback, many=True)
        context = self.get_serializer_context()
        activities_serializer = ActivitySerializer(activities, many=True, context=context)
        return self.get_paginated_response({
            'feedback': serializer.data,
            'activities': activities_serializer.data,
        })

    @action(
        detail=False,
        methods=['GET'],
        renderer_classes=(FeedbackExportRenderer, ),
        pagination_class=None,
        serializer_class=FeedbackExportSerializer,
    )
    def export(self, request, format=None):
        queryset = self.filter_queryset(self.get_queryset()) \
            .select_related('about', 'about__place', 'about__place__group') \
            .order_by('-about__date')
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
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = ActivitySeriesFilter
    permission_classes = (IsAuthenticated, IsGroupEditor)

    def get_queryset(self):
        return self.queryset.filter(place__group__members=self.request.user)

    def get_serializer_class(self):
        if self.action == 'partial_update':
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


class ActivityPagination(CursorPagination):
    """Pagination with a high number of activities in order to not break
    frontend assumptions of getting all upcoming activities per group.
    Could be reduced and add pagination handling in frontend when speed becomes an issue"""
    # TODO: create an index on 'date' for increased speed
    page_size = 400
    ordering = 'date'


class ActivityViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    """
    Activity Dates

    list:
    Query parameters
    - `?series` - filter by activity series id
    - `?place` - filter by place id
    - `?group` - filter by group id
    - `?date_min=<from_date>`&`date_max=<to_date>` - filter by date, can also either give either date_min or date_max
    """
    serializer_class = ActivitySerializer
    queryset = ActivityModel.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = ActivitiesFilter
    permission_classes = (IsAuthenticated, IsUpcoming, IsGroupEditor, IsEmptyActivity)
    pagination_class = ActivityPagination

    def get_queryset(self):
        qs = self.queryset.filter(place__group__members=self.request.user, place__status=PlaceStatus.ACTIVE.value)
        if self.action == 'list':
            # because we have participants field in the serializer
            # only prefetch on read_only actions, otherwise there are caching problems when participants get added
            qs = qs.prefetch_related('activityparticipant_set', 'feedback_given_by')
        return qs

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return ActivityUpdateSerializer
        return self.serializer_class

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasNotJoinedActivity, IsNotFull),
        serializer_class=ActivityJoinSerializer
    )
    def add(self, request, pk=None):
        return self.partial_update(request)

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasJoinedActivity),
        serializer_class=ActivityLeaveSerializer
    )
    def remove(self, request, pk=None):
        return self.partial_update(request)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this activity"""
        return self.retrieve_conversation(request, pk)
