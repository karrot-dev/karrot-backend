from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from karrot.history.filters import HistoryFilter
from karrot.history.models import History
from karrot.history.serializers import HistorySerializer, HistoryExportRenderer, HistoryExportSerializer


class HistoryPagination(CursorPagination):
    page_size = 10
    ordering = '-id'


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    History of user actions
    
    export:
    Export history as CSV
    """
    serializer_class = HistorySerializer
    queryset = History.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_class = HistoryFilter
    permission_classes = (IsAuthenticated, )
    pagination_class = HistoryPagination

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)

    @action(
        detail=False,
        methods=['GET'],
        renderer_classes=(HistoryExportRenderer, ),
        pagination_class=None,
        serializer_class=HistoryExportSerializer,
    )
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset()) \
            .select_related('group') \
            .order_by('-date')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
