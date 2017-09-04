from rest_framework import viewsets
from rest_framework.filters import DjangoFilterBackend
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated

from foodsaving.activity.filters import ActivityFilter
from foodsaving.activity.models import Activity
from foodsaving.activity.serializers import ActivitySerializer


class ActivityPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 1000


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Activity of user actions
    """
    serializer_class = ActivitySerializer
    queryset = Activity.objects
    filter_backends = (DjangoFilterBackend,)
    filter_class = ActivityFilter
    permission_classes = (IsAuthenticated,)
    pagination_class = ActivityPagination

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)
