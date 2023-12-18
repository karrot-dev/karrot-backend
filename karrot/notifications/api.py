from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.activities.models import Activity
from karrot.activities.serializers import ActivitySerializer
from karrot.applications.models import Application
from karrot.applications.serializers import ApplicationSerializer
from karrot.issues.models import Issue
from karrot.issues.serializers import IssueSerializer
from karrot.notifications.models import Notification, NotificationMeta
from karrot.notifications.serializers import NotificationSerializer, NotificationMetaSerializer


class NotificationPagination(CursorPagination):
    page_size = 20
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-id"


class NotificationViewSet(GenericViewSet):
    """
    On-site notifications (Bell)
    """

    serializer_class = NotificationSerializer
    queryset = Notification.objects
    permission_classes = (IsAuthenticated,)
    pagination_class = NotificationPagination

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        notifications = list(self.paginate_queryset(queryset))

        meta = NotificationMeta.objects.get(user=request.user)

        activities = (
            Activity.objects.filter(id__in=[n.context["activity"] for n in notifications if "activity" in n.context])
            .select_related("activity_type")
            .prefetch_related(
                "activityparticipant_set",
                "feedback_given_by",
                "participant_types",
            )
        )

        applications = Application.objects.filter(
            id__in=[n.context["application"] for n in notifications if "application" in n.context]
        ).select_related("user")

        issues = Issue.objects.filter(
            id__in=[n.context["issue"] for n in notifications if "issue" in n.context]
        ).prefetch_for_serializer(user=request.user)

        context = self.get_serializer_context()
        serializer = self.get_serializer(notifications, many=True)
        meta_serializer = NotificationMetaSerializer(meta, context=context)
        activities_serializer = ActivitySerializer(activities, many=True, context=context)
        application_serializer = ApplicationSerializer(applications, many=True, context=context)
        issue_serializer = IssueSerializer(issues, many=True, context=context)

        return self.get_paginated_response(
            {
                "notifications": serializer.data,
                "activities": activities_serializer.data,
                "applications": application_serializer.data,
                "issues": issue_serializer.data,
                "meta": meta_serializer.data,
            }
        )

    @action(detail=True, methods=["POST"])
    def mark_clicked(self, request, pk=None):
        """Mark notification as clicked"""
        self.check_permissions(request)
        notification = self.get_object()

        if not notification.clicked:
            notification.clicked = True
            notification.save()

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def mark_seen(self, request):
        """Mark all notifications as seen"""
        self.check_permissions(request)
        meta, _ = NotificationMeta.objects.update_or_create({"marked_at": timezone.now()}, user=request.user)
        serializer = NotificationMetaSerializer(meta)
        return Response(serializer.data)
