from django.db.models import Count, Q, Sum
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.activities.models import Activity
from karrot.activities.permissions import CannotChangeGroup
from karrot.conversations.api import RetrieveConversationMixin
from karrot.places.filters import PlaceStatusFilter, PlaceTypeFilter
from karrot.places.models import Place as PlaceModel
from karrot.places.models import PlaceStatus, PlaceSubscription, PlaceType
from karrot.places.permissions import IsGroupEditor, TypeHasNoPlaces
from karrot.places.serializers import (
    PlaceSerializer,
    PlaceStatusSerializer,
    PlaceSubscriptionSerializer,
    PlaceTypeSerializer,
    PlaceUpdateSerializer,
)
from karrot.utils.mixins import PartialUpdateModelMixin


class PlaceTypeViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PlaceTypeSerializer
    queryset = PlaceType.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PlaceTypeFilter
    permission_classes = (
        IsAuthenticated,
        IsGroupEditor,
        TypeHasNoPlaces,
        CannotChangeGroup,
    )

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)


class PlaceStatusViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PlaceStatusSerializer
    queryset = PlaceStatus.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PlaceStatusFilter
    permission_classes = (
        IsAuthenticated,
        IsGroupEditor,
        TypeHasNoPlaces,
        CannotChangeGroup,
    )

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)


class PlaceViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
    RetrieveConversationMixin,
):
    """
    Places

    # Query parameters
    - `?group` - filter by place group id
    - `?search` - search in name and description
    """

    serializer_class = PlaceSerializer
    queryset = PlaceModel.objects
    filterset_fields = ("group", "name")
    filter_backends = (SearchFilter, filters.DjangoFilterBackend)
    search_fields = ("name", "description")
    permission_classes = (IsAuthenticated, IsGroupEditor)

    def get_queryset(self):
        qs = self.queryset.filter(group__members=self.request.user)
        if self.action == "list":
            qs = qs.prefetch_related("subscribers")
        if self.action == "statistics":
            return qs.annotate(
                feedback_count=Count("activities__feedback", distinct=True),
                activities_done=Count("activities", filter=Q(activities__in=Activity.objects.done()), distinct=True),
            )
        else:
            return qs

    def get_serializer_class(self):
        if self.action == "partial_update":
            return PlaceUpdateSerializer
        return self.serializer_class

    @action(detail=True)
    def statistics(self, request, pk=None):
        instance = self.get_object()

        weight = instance.activities.annotate_feedback_weight().aggregate(result_weight=Sum("feedback_weight"))[
            "result_weight"
        ]

        data = {
            "feedback_count": instance.feedback_count,
            "feedback_weight": round(weight or 0),
            "activities_done": instance.activities_done,
        }
        return Response(data)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this place"""
        return self.retrieve_conversation(request, pk)

    @action(
        detail=True,
        methods=["POST", "DELETE"],
        serializer_class=PlaceSubscriptionSerializer,
    )
    def subscription(self, request, pk):
        self.check_permissions(request)
        place = self.get_object()
        self.check_object_permissions(request, place)

        if request.method == "POST":
            serializer = self.get_serializer(data={"place": place.id})
            serializer.is_valid(raise_exception=True)
            subscription = serializer.save()

            serializer = self.get_serializer(instance=subscription)
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)

        if request.method == "DELETE":
            deleted_rows, _ = PlaceSubscription.objects.filter(place=place, user=self.request.user).delete()
            deleted = deleted_rows > 0

            return Response(
                data={},
                status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND,
            )
