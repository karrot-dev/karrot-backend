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
from karrot.pickups.filters import (PickupDatesFilter, PickupDateSeriesFilter, FeedbackFilter)
from karrot.pickups.models import (
    PickupDate as PickupDateModel, PickupDateSeries as PickupDateSeriesModel, Feedback as FeedbackModel
)
from karrot.pickups.permissions import (
    IsUpcoming, HasNotJoinedPickupDate, HasJoinedPickupDate, IsEmptyPickupDate, IsNotFull, IsSameCollector,
    IsRecentPickupDate, IsGroupEditor
)
from karrot.pickups.serializers import (
    PickupDateSerializer, PickupDateSeriesSerializer, PickupDateJoinSerializer, PickupDateLeaveSerializer,
    FeedbackSerializer, PickupDateUpdateSerializer, PickupDateSeriesUpdateSerializer,
    PickupDateSeriesHistorySerializer, FeedbackExportSerializer, FeedbackExportRenderer
)
from karrot.utils.mixins import PartialUpdateModelMixin


class FeedbackPagination(CursorPagination):
    page_size = 10
    ordering = '-id'


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
    - `?about` - filter by pickup id
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
    permission_classes = (IsAuthenticated, IsSameCollector, IsRecentPickupDate)
    pagination_class = FeedbackPagination

    def get_queryset(self):
        return self.queryset.filter(about__place__group__members=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()) \
            .select_related('about') \
            .prefetch_related('about__pickupdatecollector_set', 'about__feedback_given_by')
        feedback = self.paginate_queryset(queryset)

        pickups = set(f.about for f in feedback)

        serializer = self.get_serializer(feedback, many=True)
        context = self.get_serializer_context()
        pickups_serializer = PickupDateSerializer(pickups, many=True, context=context)
        return self.get_paginated_response({
            'feedback': serializer.data,
            'pickups': pickups_serializer.data,
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


class PickupDateSeriesViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        mixins.DestroyModelMixin,
        viewsets.GenericViewSet,
):

    serializer_class = PickupDateSeriesSerializer
    queryset = PickupDateSeriesModel.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = PickupDateSeriesFilter
    permission_classes = (IsAuthenticated, IsGroupEditor)

    def get_queryset(self):
        return self.queryset.filter(place__group__members=self.request.user)

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return PickupDateSeriesUpdateSerializer
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
            before=PickupDateSeriesHistorySerializer(series).data,
        )
        super().perform_destroy(series)
        series.place.group.refresh_active_status()


class PickupDatePagination(CursorPagination):
    """Pagination with a high number of pickup dates in order to not break
    frontend assumptions of getting all upcoming pickup dates per group.
    Could be reduced and add pagination handling in frontend when speed becomes an issue"""
    # TODO: create an index on 'date' for increased speed
    page_size = 400
    ordering = 'date'


class PickupDateViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    """
    Pickup Dates

    list:
    Query parameters
    - `?series` - filter by pickup date series id
    - `?place` - filter by place id
    - `?group` - filter by group id
    - `?date_min=<from_date>`&`date_max=<to_date>` - filter by date, can also either give either date_min or date_max
    """
    serializer_class = PickupDateSerializer
    queryset = PickupDateModel.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = PickupDatesFilter
    permission_classes = (IsAuthenticated, IsUpcoming, IsGroupEditor, IsEmptyPickupDate)
    pagination_class = PickupDatePagination

    def get_queryset(self):
        qs = self.queryset.filter(place__group__members=self.request.user, place__status='active')
        if self.action == 'list':
            # because we have collectors field in the serializer
            # only prefetch on read_only actions, otherwise there are caching problems when collectors get added
            qs = qs.prefetch_related('pickupdatecollector_set', 'feedback_given_by')
        return qs

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return PickupDateUpdateSerializer
        return self.serializer_class

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasNotJoinedPickupDate, IsNotFull),
        serializer_class=PickupDateJoinSerializer
    )
    def add(self, request, pk=None):
        return self.partial_update(request)

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasJoinedPickupDate),
        serializer_class=PickupDateLeaveSerializer
    )
    def remove(self, request, pk=None):
        return self.partial_update(request)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this pickup"""
        return self.retrieve_conversation(request, pk)
