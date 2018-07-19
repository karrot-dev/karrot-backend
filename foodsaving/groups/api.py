import pytz
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.groups import roles, stats
from foodsaving.groups.filters import GroupsFilter, GroupsInfoFilter
from foodsaving.groups.models import Agreement, Group as GroupModel, GroupMembership
from foodsaving.groups.serializers import GroupDetailSerializer, GroupPreviewSerializer, GroupJoinSerializer, \
    GroupLeaveSerializer, TimezonesSerializer, EmptySerializer, \
    GroupMembershipAddRoleSerializer, GroupMembershipRemoveRoleSerializer, GroupMembershipInfoSerializer, \
    AgreementSerializer, AgreementAgreeSerializer, GroupMembershipAddNotificationTypeSerializer, \
    GroupMembershipRemoveNotificationTypeSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class IsNotMember(BasePermission):
    message = _('You are already a member.')

    def has_object_permission(self, request, view, obj):
        return not obj.is_member(request.user)


class IsOpenGroup(BasePermission):
    message = _('You can only join open groups.')

    def has_object_permission(self, request, view, obj):
        return obj.is_open


class CanUpdateMemberships(BasePermission):
    message = _('You do not have permission to update memberships.')

    def has_object_permission(self, request, view, obj):
        # we get a membership object
        return obj.group.is_member_with_role(request.user, roles.GROUP_MEMBERSHIP_MANAGER)


class GroupInfoViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    """
    Group Info - public information

    # Query parameters
    - `?members` - filter by member user id
    - `?search` - search in name and public description
    - `?include_empty` - set to False to exclude empty groups without members
    """
    queryset = GroupModel.objects.prefetch_related('members')
    filter_backends = (SearchFilter, DjangoFilterBackend)
    filter_class = GroupsInfoFilter
    search_fields = ('name', 'public_description')
    serializer_class = GroupPreviewSerializer


class GroupViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin, mixins.ListModelMixin,
                   RetrieveConversationMixin, GenericViewSet):
    """
    Your groups: list, create, update
    """
    queryset = GroupModel.objects
    filter_backends = (SearchFilter, DjangoFilterBackend)
    filter_class = GroupsFilter
    search_fields = ('name', 'public_description')
    serializer_class = GroupDetailSerializer
    permission_classes = (IsAuthenticated, )

    def create(self, request, *args, **kwargs):
        """Create a new group"""
        return super().create(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Get details to one of your groups"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List your groups

        # Query parameters
        - `?members` - filter by member user id
        - `?search` - search in name and public description
        """
        return super().list(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Update one of your groups"""
        return super().partial_update(request, *args, **kwargs)

    def get_queryset(self):
        if self.action == 'join':
            return self.queryset
        return self.queryset.filter(members=self.request.user)

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsNotMember, IsOpenGroup),
        serializer_class=GroupJoinSerializer
    )
    def join(self, request, pk=None):
        """Join a group"""
        return self.partial_update(request)

    @action(detail=True, methods=['POST'], serializer_class=GroupLeaveSerializer)
    def leave(self, request, pk=None):
        """Leave one of your groups"""
        return self.partial_update(request)

    @action(detail=False, methods=['GET'], serializer_class=TimezonesSerializer)
    def timezones(self, request, pk=None):
        """List all accepted timezones"""
        return Response(self.get_serializer({'all_timezones': pytz.all_timezones}).data)

    @action(detail=True)
    def conversation(self, request, pk=None):
        """Get wall conversation ID of this group"""
        return self.retrieve_conversation(request, pk)

    @action(detail=True, methods=['POST'])
    def mark_user_active(self, request, pk=None):
        """Mark that the logged-in user is active in the group"""
        gm = get_object_or_404(GroupMembership.objects, group=pk, user=request.user)
        gm.lastseen_at = timezone.now()
        gm.inactive_at = None
        gm.save()
        stats.group_activity(gm.group)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['PUT', 'DELETE'],
        permission_classes=(IsAuthenticated, CanUpdateMemberships),
        url_name='user-roles',
        url_path='users/(?P<user_id>[^/.]+)/roles/(?P<role_name>[^/.]+)',
        serializer_class=EmptySerializer  # for Swagger
    )
    def modify_user_roles(self, request, pk, user_id, role_name):
        """add (POST) or remove (DELETE) a membership role"""
        instance = get_object_or_404(GroupMembership.objects, group=pk, user=user_id)
        self.check_object_permissions(request, instance)
        serializer_class = None
        if request.method == 'PUT':
            serializer_class = GroupMembershipAddRoleSerializer
        elif request.method == 'DELETE':
            serializer_class = GroupMembershipRemoveRoleSerializer
        serializer = serializer_class(instance, data={'role_name': role_name}, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(GroupMembershipInfoSerializer(instance).data)

    @action(
        detail=True,
        methods=['PUT', 'DELETE'],
        permission_classes=(IsAuthenticated, ),
        url_name='notification_types',
        url_path='notification_types/(?P<notification_type>[^/.]+)',
        serializer_class=EmptySerializer  # for Swagger
    )
    def modify_notification_types(self, request, pk, notification_type):
        """add (POST) or remove (DELETE) a notification type"""
        membership = get_object_or_404(GroupMembership.objects, group=self.get_object(), user=request.user)
        self.check_object_permissions(request, membership)
        serializer_class = None
        if request.method == 'PUT':
            serializer_class = GroupMembershipAddNotificationTypeSerializer
        elif request.method == 'DELETE':
            serializer_class = GroupMembershipRemoveNotificationTypeSerializer
        serializer = serializer_class(membership, data={'notification_type': notification_type}, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(GroupMembershipInfoSerializer(membership).data)


class AgreementViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, PartialUpdateModelMixin,
                       mixins.ListModelMixin, GenericViewSet):
    queryset = Agreement.objects
    serializer_class = AgreementSerializer
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)

    @action(
        detail=True,
        methods=['POST'],
        serializer_class=AgreementAgreeSerializer,
    )
    def agree(self, request, pk=None):
        return self.partial_update(request)
