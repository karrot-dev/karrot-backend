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


class HasVerifiedEmailAddress(permissions.BasePermission):
    message = _('You need to have a verified email address')

    def has_permission(self, request, view):
        return request.user.mail_verified


class GroupApplicationViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              GenericViewSet):
    queryset = GroupApplication.objects
    serializer_class = GroupApplicationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (DjangoFilterBackend, )
    filter_fields = ('group', )

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes.append(HasVerifiedEmailAddress)
        return super().get_permissions()

    def get_queryset(self):
        q = Q(group__members=self.request.user)
        if self.action in ('list', 'retrieve'):
            q |= Q(user=self.request.user)
        if self.action == 'withdraw':
            q = Q(user=self.request.user)
        return self.queryset.filter(q)

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
