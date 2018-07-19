from django.db.models import Avg, Count, Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.pickups.models import PickupDate
from foodsaving.stores.models import Store as StoreModel
from foodsaving.stores.serializers import StoreSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class StoreViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin, mixins.ListModelMixin,
                   GenericViewSet):
    """
    Stores

    # Query parameters
    - `?group` - filter by store group id
    - `?search` - search in name and description
    """
    serializer_class = StoreSerializer
    queryset = StoreModel.objects.filter(deleted=False)
    filter_fields = ('group', 'name')
    filter_backends = (SearchFilter, DjangoFilterBackend)
    search_fields = ('name', 'description')
    permission_classes = (IsAuthenticated, )

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
