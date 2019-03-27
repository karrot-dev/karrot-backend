from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.notifications.models import Notification, NotificationMeta
from karrot.notifications.serializers import NotificationSerializer, NotificationMetaSerializer


class NotificationPagination(CursorPagination):
    page_size = 20
    ordering = '-id'


class NotificationViewSet(GenericViewSet):
    """
    On-site notifications (Bell)
    """
    serializer_class = NotificationSerializer
    queryset = Notification.objects
    permission_classes = (IsAuthenticated, )
    pagination_class = NotificationPagination

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)

        meta, _ = NotificationMeta.objects.get_or_create(user=request.user)
        meta_serializer = NotificationMetaSerializer(meta, context=self.get_serializer_context())

        return self.get_paginated_response({
            'notifications': serializer.data,
            'meta': meta_serializer.data,
        })

    @action(detail=True, methods=['POST'])
    def mark_clicked(self, request, pk=None):
        """Mark notification as clicked"""
        self.check_permissions(request)
        notification = self.get_object()

        if not notification.clicked:
            notification.clicked = True
            notification.save()

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['POST'])
    def mark_seen(self, request):
        """Mark all notifications as seen"""
        self.check_permissions(request)
        meta, _ = NotificationMeta.objects.update_or_create({'marked_at': timezone.now()}, user=request.user)
        serializer = NotificationMetaSerializer(meta)
        return Response(serializer.data)
