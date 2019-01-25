from django.db.models import Avg, Count, Q, Sum
from django_filters import rest_framework as filters
from django.utils.translation import ugettext_lazy as _
from rest_framework import mixins, permissions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.pickups.models import PickupDate
from foodsaving.stores.models import Store as StoreModel
from foodsaving.stores.serializers import StoreSerializer, StoreUpdateSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class IsGroupEditor(permissions.BasePermission):
    message = _('You need to be a group editor')

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.group.is_editor(request.user)
        return True


class StoreViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    """
    Stores

    # Query parameters
    - `?group` - filter by store group id
    - `?search` - search in name and description
    """
    serializer_class = StoreSerializer
    queryset = StoreModel.objects
    filterset_fields = ('group', 'name')
    filter_backends = (SearchFilter, filters.DjangoFilterBackend)
    search_fields = ('name', 'description')
    permission_classes = (IsAuthenticated, IsGroupEditor)

    def get_queryset(self):
        qs = self.queryset.filter(group__members=self.request.user)
        if self.action == 'statistics':
            return qs.annotate(
                feedback_count=Count('pickup_dates__feedback', distinct=True),
                pickups_done=Count(
                    'pickup_dates', filter=Q(pickup_dates__in=PickupDate.objects.done()), distinct=True
                )
            )
        else:
            return qs

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return StoreUpdateSerializer
        return self.serializer_class

    @action(detail=True)
    def statistics(self, request, pk=None):
        instance = self.get_object()
        weight = instance.pickup_dates.annotate(avg_weight=Avg('feedback__weight'))\
            .aggregate(estimated_weight=Sum('avg_weight'))['estimated_weight']
        data = {
            'feedback_count': instance.feedback_count,
            'feedback_weight': round(weight or 0),
            'pickups_done': instance.pickups_done,
        }
        return Response(data)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this store"""
        return self.retrieve_conversation(request, pk)
