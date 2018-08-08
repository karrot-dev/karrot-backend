from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.applications.models import GroupApplication
from foodsaving.applications.serializers import GroupApplicationSerializer


class HasVerifiedEmailAddress(permissions.BasePermission):
    message = _('You need to have a verified email address')

    def has_permission(self, request, view):
        if view.action != 'create':
            return True
        return request.user.mail_verified


class IsGroupEditor(permissions.BasePermission):
    message = _('You need to be a group editor')

    def has_object_permission(self, request, view, obj):
        application = obj
        return application.group.is_editor(request.user)


class IsApplicant(permissions.BasePermission):
    message = _('You need to be the applicant')

    def has_object_permission(self, request, view, obj):
        application = obj
        return application.user == request.user


class GroupApplicationViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    queryset = GroupApplication.objects
    serializer_class = GroupApplicationSerializer
    permission_classes = (
        IsAuthenticated,
        HasVerifiedEmailAddress,
    )
    filter_backends = (DjangoFilterBackend, )
    filterset_fields = ('group', 'user', 'status')

    def get_queryset(self):
        return self.queryset.filter(Q(group__members=self.request.user) | Q(user=self.request.user)).distinct()

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsGroupEditor),
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
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsGroupEditor),
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
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsApplicant),
    )
    def withdraw(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.withdraw()
        serializer = self.get_serializer(application)
        return Response(data=serializer.data)
