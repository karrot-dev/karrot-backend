from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups.filters import (PickupDatesFilter, PickupDateSeriesFilter, FeedbackFilter)
from foodsaving.pickups.models import (
    PickupDate as PickupDateModel, PickupDateSeries as PickupDateSeriesModel, Feedback as FeedbackModel
)
from foodsaving.pickups.permissions import (
    IsUpcoming, HasNotJoinedPickupDate, HasJoinedPickupDate, IsEmptyPickupDate, IsNotFull, IsSameCollector,
    IsRecentPickupDate, IsGroupEditor
)
from foodsaving.pickups.serializers import (
    PickupDateSerializer, PickupDateSeriesSerializer, PickupDateJoinSerializer, PickupDateLeaveSerializer,
    FeedbackSerializer, PickupDateHistorySerializer, PickupDateSeriesCancelSerializer, PickupDateUpdateSerializer,
    PickupDateSeriesUpdateSerializer
)
from foodsaving.utils.mixins import PartialUpdateModelMixin


class FeedbackPagination(CursorPagination):
    # TODO: create an index on 'created_at' for increased speed
    page_size = 10
    ordering = '-created_at'


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
    - `?store` - filter by store id
    - `?group` - filter by group id
    - `?created_at_min` and `?created_at_max` - filter by creation date
    """
    serializer_class = FeedbackSerializer
    queryset = FeedbackModel.objects.all()
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = FeedbackFilter
    permission_classes = (IsAuthenticated, IsSameCollector, IsRecentPickupDate)
    pagination_class = FeedbackPagination

    def get_queryset(self):
        return self.queryset.filter(about__store__group__members=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()) \
            .select_related('about') \
            .prefetch_related('about__collectors')
        feedback = self.paginate_queryset(queryset)

        pickups = set(f.about for f in feedback)

        serializer = self.get_serializer(feedback, many=True)
        context = self.get_serializer_context()
        pickups_serializer = PickupDateSerializer(pickups, many=True, context=context)
        return self.get_paginated_response({
            'feedback': serializer.data,
            'pickups': pickups_serializer.data,
        })


class PickupDateSeriesViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        viewsets.GenericViewSet,
):

    serializer_class = PickupDateSeriesSerializer
    queryset = PickupDateSeriesModel.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = PickupDateSeriesFilter
    permission_classes = (IsAuthenticated, IsGroupEditor)

    def get_queryset(self):
        return self.queryset.filter(store__group__members=self.request.user)

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return PickupDateSeriesUpdateSerializer
        return self.serializer_class

    @action(
        detail=True,
        methods=['POST'],
        serializer_class=PickupDateSeriesCancelSerializer,
    )
    def cancel(self, request, *args, **kwargs):
        """Cancel upcoming pickups and delete this series"""
        series = self.get_object()
        serializer = self.get_serializer(series, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @action(
        detail=True,
        methods=['POST'],
        serializer_class=PickupDateSeriesUpdateSerializer,
    )
    def get_pickup_preview(self, request, *args, **kwargs):
        """Returns an overview which pickups will get created or cancelled when modifying the series"""
        series = self.get_object()
        serializer = self.get_serializer(series, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        preview = series.preview_override_pickups(
            rule=serializer.validated_data.get('rule'), start_date=serializer.validated_data.get('start_date')
        )

        return Response([{
            'existing_pickup': PickupDateSerializer(pickup).data if pickup else None,
            'new_date': date.isoformat() if date else None,
        } for (pickup, date) in preview])


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
        mixins.DestroyModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    """
    Pickup Dates

    list:
    Query parameters
    - `?series` - filter by pickup date series id
    - `?store` - filter by store id
    - `?group` - filter by group id
    - `?date_min=<from_date>`&`date_max=<to_date>` - filter by date, can also either give either date_min or date_max
    """
    serializer_class = PickupDateSerializer
    queryset = PickupDateModel.objects \
        .filter(deleted=False)
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = PickupDatesFilter
    permission_classes = (IsAuthenticated, IsUpcoming, IsGroupEditor, IsEmptyPickupDate)
    pagination_class = PickupDatePagination

    def get_queryset(self):
        qs = self.queryset.filter(store__group__members=self.request.user, store__status='active')
        if self.action == 'list':
            # because we have collector_ids field in the serializer
            # only prefetch on read_only actions, otherwise there are caching problems when collectors get added
            qs = qs.prefetch_related('collectors')
        return qs

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return PickupDateUpdateSerializer
        return self.serializer_class

    def perform_destroy(self, pickup):
        # set deleted flag to make the pickup date invisible
        pickup.deleted = True

        History.objects.create(
            typus=HistoryTypus.PICKUP_DELETE,
            group=pickup.store.group,
            store=pickup.store,
            users=[
                self.request.user,
            ],
            before=PickupDateHistorySerializer(pickup).data,
        )
        pickup.save()

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
