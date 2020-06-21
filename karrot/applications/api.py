from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import permissions, mixins
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from karrot.applications.models import Application, ApplicationStatus
from karrot.applications.serializers import ApplicationSerializer
from karrot.conversations.api import RetrieveConversationMixin


class ApplicationsPerDayThrottle(UserRateThrottle):
    rate = "20/day"


class ApplicationPagination(CursorPagination):
    page_size = 20
    ordering = "-id"


class HasVerifiedEmailAddress(permissions.BasePermission):
    message = _("You need to have a verified email address")

    def has_permission(self, request, view):
        if view.action != "create":
            return True
        return request.user.mail_verified


class IsGroupEditor(permissions.BasePermission):
    message = _("You need to be a group editor")

    def has_object_permission(self, request, view, obj):
        application = obj
        return application.group.is_editor(request.user)


class IsApplicant(permissions.BasePermission):
    message = _("You need to be the applicant")

    def has_object_permission(self, request, view, obj):
        application = obj
        return application.user == request.user


class IsPending(permissions.BasePermission):
    message = _("Application is not pending anymore")

    def has_object_permission(self, request, view, obj):
        application = obj
        return application.status == ApplicationStatus.PENDING.value


class ApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
    RetrieveConversationMixin,
):
    queryset = Application.objects
    serializer_class = ApplicationSerializer
    permission_classes = (
        IsAuthenticated,
        HasVerifiedEmailAddress,
    )
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_fields = ("group", "user", "status")
    pagination_class = ApplicationPagination

    def get_throttles(self):
        if self.action == "create":
            self.throttle_classes = (ApplicationsPerDayThrottle,)
        return super().get_throttles()

    def get_queryset(self):
        return self.queryset.filter(
            Q(group__members=self.request.user) | Q(user=self.request.user)
        ).distinct()

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, IsGroupEditor, IsPending),
    )
    def accept(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.accept(self.request.user)
        serializer = self.get_serializer(application)
        return Response(data=serializer.data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, IsGroupEditor, IsPending),
    )
    def decline(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.decline(self.request.user)
        serializer = self.get_serializer(application)
        return Response(data=serializer.data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=(IsAuthenticated, IsApplicant, IsPending),
    )
    def withdraw(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.withdraw()
        serializer = self.get_serializer(application)
        return Response(data=serializer.data)

    @action(detail=True,)
    def conversation(self, request, pk=None):
        """Get conversation ID of this application"""
        return self.retrieve_conversation(request, pk)
