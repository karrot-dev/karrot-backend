from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated

from karrot.history.filters import HistoryFilter
from karrot.history.models import History
from karrot.history.serializers import HistorySerializer


class HistoryPagination(CursorPagination):
    # TODO: create an index on 'date' for increased speed
    page_size = 10
    ordering = '-date'


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    History of user actions
    """
    serializer_class = HistorySerializer
    queryset = History.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = HistoryFilter
    permission_classes = (IsAuthenticated, )
    pagination_class = HistoryPagination

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)
