from rest_framework import mixins
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.notifications.models import Notification
from foodsaving.notifications.serializers import NotificationSerializer


class NotificationPagination(CursorPagination):
    # TODO: create an index on 'created_at' for increased speed
    page_size = 20
    ordering = '-created_at'


class NotificationViewSet(
        mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    """
    Notification-type notifications
    """
    serializer_class = NotificationSerializer
    queryset = Notification.objects
    permission_classes = (IsAuthenticated, )
    pagination_class = NotificationPagination

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
