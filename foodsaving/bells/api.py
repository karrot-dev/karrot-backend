from rest_framework import mixins
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.bells.models import Bell
from foodsaving.bells.serializers import BellSerializer


class BellPagination(CursorPagination):
    # TODO: create an index on 'created_at' for increased speed
    page_size = 20
    ordering = '-created_at'


class BellViewSet(
        mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    """
    Bell-type notifications
    """
    serializer_class = BellSerializer
    queryset = Bell.objects
    permission_classes = (IsAuthenticated, )
    pagination_class = BellPagination

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
