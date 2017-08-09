from django.dispatch import Signal
from rest_framework import filters
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.stores.filters import PickupDatesFilter, PickupDateSeriesFilter
from foodsaving.stores.permissions import (
    IsUpcoming, HasNotJoinedPickupDate, HasJoinedPickupDate, IsEmptyPickupDate,
    IsNotFull)
from foodsaving.stores.serializers import (
    StoreSerializer, PickupDateSerializer, PickupDateSeriesSerializer,
    PickupDateJoinSerializer, PickupDateLeaveSerializer, FeedbackSerializer)
from foodsaving.stores.models import (
    Store as StoreModel,
    PickupDate as PickupDateModel,
    PickupDateSeries as PickupDateSeriesModel,
    Feedback as FeedbackModel
)
from foodsaving.utils.mixins import PartialUpdateModelMixin

pre_pickup_delete = Signal()
pre_series_delete = Signal()
post_store_delete = Signal()
post_feedback_delete = Signal()


class StoreViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    Stores

    # Query parameters
    - `?group` - filter by store group id
    - `?search` - search in name and description
    """
    serializer_class = StoreSerializer
    queryset = StoreModel.objects.filter(deleted=False)
    filter_fields = ('group', 'name')
    filter_backends = (filters.SearchFilter, filters.DjangoFilterBackend)
    search_fields = ('name', 'description')
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)

    def perform_destroy(self, store):
        store.deleted = True
        store.save()
        post_store_delete.send(
            sender=self.__class__,
            group=store.group,
            store=store,
            user=self.request.user,
        )
        # implicit action: delete all pickups and series, but don't send out signals for them
        PickupDateModel.objects.filter(store=store).delete()
        PickupDateSeriesModel.objects.filter(store=store).delete()


class FeedbackViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    # PartialUpdateModelMixin,
    # mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    serializer_class = FeedbackSerializer
    queryset = FeedbackModel.objects.all()

    """
    Feedback

    # Query parameters
    -
    # filter_fields = ('group', 'name')

    def get_queryset(self):
        return self.queryset.all()

    def perform_destroy(self, feedback):
        feedback.deleted = True
        feedback.save()
        post_feedback_delete.send(
            sender=self.__class__,
            group=feedback.group,
            feedback=feedback,
            user=self.request.user,
        )
        feedback.save()
         `?user` - filter by user id
    """


class PickupDateSeriesViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """
    Pickup Date Series

    # Query parameters
    - `?store` - filter by store id
    """
    serializer_class = PickupDateSeriesSerializer
    queryset = PickupDateSeriesModel.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = PickupDateSeriesFilter
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.filter(store__group__members=self.request.user)

    def perform_destroy(self, series):
        pre_series_delete.send(
            sender=self.__class__,
            group=series.store.group,
            store=series.store,
            user=self.request.user,
        )
        super().perform_destroy(series)


class PickupDateViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    Pickup Dates

    # Query parameters
    - `?series` - filter by pickup date series id
    - `?store` - filter by store id
    - `?group` - filter by group id
    - `?date_0=<from_date>`&`date_1=<to_date>` - filter by date, can also either give date_0 or date_1
    """
    serializer_class = PickupDateSerializer
    queryset = PickupDateModel.objects.filter(deleted=False)
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = PickupDatesFilter
    permission_classes = (IsAuthenticated, IsUpcoming)

    def get_permissions(self):
        if self.action == 'destroy':
            self.permission_classes = (IsAuthenticated, IsUpcoming, IsEmptyPickupDate,)

        return super().get_permissions()

    def get_queryset(self):
        return self.queryset.filter(store__group__members=self.request.user)

    def perform_destroy(self, pickup):
        # set deleted flag to make the pickup date invisible
        pickup.deleted = True

        pre_pickup_delete.send(
            sender=self.__class__,
            group=pickup.store.group,
            store=pickup.store,
            user=self.request.user
        )
        pickup.save()

    @detail_route(
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasNotJoinedPickupDate, IsNotFull),
        serializer_class=PickupDateJoinSerializer
    )
    def add(self, request, pk=None):
        return self.partial_update(request)

    @detail_route(
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsUpcoming, HasJoinedPickupDate),
        serializer_class=PickupDateLeaveSerializer
    )
    def remove(self, request, pk=None):
        return self.partial_update(request)
