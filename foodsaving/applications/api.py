from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.applications import stats
from foodsaving.applications.models import GroupApplication
from foodsaving.applications.serializers import GroupApplicationSerializer
from foodsaving.groups.models import Group


class HasVerifiedEmailAddress(permissions.BasePermission):
    message = _('You need to have a verified email address')

    def has_permission(self, request, view):
        if view.action != 'create':
            return True
        return request.user.mail_verified


class GroupApplicationViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              GenericViewSet):
    queryset = GroupApplication.objects
    serializer_class = GroupApplicationSerializer
    permission_classes = (
        IsAuthenticated,
        HasVerifiedEmailAddress,
    )
    filter_backends = (DjangoFilterBackend, )
    filter_fields = ('group', 'user')

    def get_queryset(self):
        q = Q(group__in=Group.objects.user_is_editor(self.request.user))
        if self.action in ('list', 'retrieve'):
            q |= Q(user=self.request.user)
        if self.action == 'withdraw':
            q = Q(user=self.request.user)
        return self.queryset.filter(q).distinct()

    @action(
        detail=True,
        methods=['POST'],
    )
    def accept(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.accept(self.request.user)
        serializer = self.get_serializer(application)
        stats.application_status_update(application)
        return Response(data=serializer.data)

    @action(
        detail=True,
        methods=['POST'],
    )
    def decline(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.decline(self.request.user)
        serializer = self.get_serializer(application)
        stats.application_status_update(application)
        return Response(data=serializer.data)

    @action(
        detail=True,
        methods=['POST'],
    )
    def withdraw(self, request, pk=None):
        self.check_permissions(request)
        application = self.get_object()
        self.check_object_permissions(request, application)

        application.withdraw()
        serializer = self.get_serializer(application)
        stats.application_status_update(application)
        return Response(data=serializer.data)
