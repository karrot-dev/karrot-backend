from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups.filters import (PickupDatesFilter, PickupDateSeriesFilter, FeedbackFilter)
from foodsaving.pickups.models import (
    PickupDate as PickupDateModel, PickupDateSeries as PickupDateSeriesModel, Feedback as FeedbackModel
)
from foodsaving.pickups.permissions import (
    IsUpcoming, HasNotJoinedPickupDate, HasJoinedPickupDate, IsEmptyPickupDate, IsNotFull, IsSameCollector,
    IsRecentPickupDate
)
from foodsaving.pickups.serializers import (
    PickupDateSerializer, PickupDateSeriesSerializer, PickupDateJoinSerializer, PickupDateLeaveSerializer,
    FeedbackSerializer
)
from foodsaving.utils.mixins import PartialUpdateModelMixin


class FeedbackPagination(CursorPagination):
    # TODO: create an index on 'created_at' for increased speed
    page_size = 10
    ordering = '-created_at'


class FeedbackViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin,
                      mixins.ListModelMixin, GenericViewSet):
    """
    Feedback

    # Query parameters
    - `?given_by` - filter by user id
    - `?about` - filter by pickup id
    - `?store` - filter by store id
    - `?group` - filter by group id
    - `?created_at_0` and `?created_at_1` - filter by creation date
    """
    serializer_class = FeedbackSerializer
    queryset = FeedbackModel.objects.all()
    filter_backends = (DjangoFilterBackend, )
    filter_class = FeedbackFilter
    permission_classes = (IsAuthenticated, )
    pagination_class = FeedbackPagination

    def get_queryset(self):
        return self.queryset.filter(about__store__group__members=self.request.user)

    def get_permissions(self):
        if self.action == 'partial_update':
            self.permission_classes = (IsAuthenticated, IsSameCollector, IsRecentPickupDate)

        return super().get_permissions()


class PickupDateSeriesViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin,
                              mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):

    serializer_class = PickupDateSeriesSerializer
    queryset = PickupDateSeriesModel.objects
    filter_backends = (DjangoFilterBackend, )
    filter_class = PickupDateSeriesFilter
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        return self.queryset.filter(store__group__members=self.request.user)

    def perform_destroy(self, series):
        History.objects.create(
            typus=HistoryTypus.SERIES_DELETE,
            group=series.store.group,
            store=series.store,
            users=[
                self.request.user,
            ],
        )
        super().perform_destroy(series)


class PickupDatePagination(CursorPagination):
    """Pagination with a high number of pickup dates in order to not break
    frontend assumptions of getting all upcoming pickup dates per group.
    Could be reduced and add pagination handling in frontend when speed becomes an issue"""
    # TODO: create an index on 'date' for increased speed
    page_size = 400
    ordering = 'date'


class PickupDateViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin,
                        mixins.DestroyModelMixin, mixins.ListModelMixin, GenericViewSet, RetrieveConversationMixin):
    """
    Pickup Dates

    list:
    Query parameters
    - `?series` - filter by pickup date series id
    - `?store` - filter by store id
    - `?group` - filter by group id
    - `?date_0=<from_date>`&`date_1=<to_date>` - filter by date, can also either give date_0 or date_1
    """
    serializer_class = PickupDateSerializer
    queryset = PickupDateModel.objects \
        .filter(deleted=False) \
        .prefetch_related('collectors')  # because we have collector_ids field in the serializer
    filter_backends = (DjangoFilterBackend, )
    filter_class = PickupDatesFilter
    permission_classes = (IsAuthenticated, IsUpcoming)
    pagination_class = PickupDatePagination

    def get_permissions(self):
        if self.action == 'destroy':
            self.permission_classes = (
                IsAuthenticated,
                IsUpcoming,
                IsEmptyPickupDate,
            )

        return super().get_permissions()

    def get_queryset(self):
        return self.queryset.filter(store__group__members=self.request.user, store__status='active')

    def perform_destroy(self, pickup):
        # set deleted flag to make the pickup date invisible
        pickup.deleted = True

        History.objects.create(
            typus=HistoryTypus.PICKUP_DELETE,
            group=pickup.store.group,
            store=pickup.store,
            users=[
                self.request.user,
            ]
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
