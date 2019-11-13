import pytz
from django.http import HttpResponseRedirect, Http404
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrieveConversationMixin
from karrot.groups import stats
from karrot.groups.filters import GroupsFilter, GroupsInfoFilter
from karrot.groups.models import Agreement, Group as GroupModel, GroupMembership, Trust
from karrot.groups.serializers import GroupDetailSerializer, GroupPreviewSerializer, GroupJoinSerializer, \
    GroupLeaveSerializer, TimezonesSerializer, EmptySerializer, \
    GroupMembershipInfoSerializer, \
    AgreementSerializer, AgreementAgreeSerializer, GroupMembershipAddNotificationTypeSerializer, \
    GroupMembershipRemoveNotificationTypeSerializer
from karrot.utils.mixins import PartialUpdateModelMixin


class IsNotMember(BasePermission):
    message = _('You are already a member.')

    def has_object_permission(self, request, view, obj):
        return not obj.is_member(request.user)


class IsOpenGroup(BasePermission):
    message = _('You can only join open groups.')

    def has_object_permission(self, request, view, obj):
        return obj.is_open


class IsOtherUser(BasePermission):
    message = _('You cannot give trust to yourself')

    def has_object_permission(self, request, view, membership):
        return membership.user != request.user


class IsGroupEditor(BasePermission):
    message = _('You need to be a group editor')

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.is_editor(request.user)
        return True


class GroupInfoViewSet(
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    """
    Group Info - public information

    # Query parameters
    - `?members` - filter by member user id
    - `?search` - search in name and public description
    - `?include_empty` - set to False to exclude empty groups without members
    """
    queryset = GroupModel.objects.prefetch_related('members')
    filter_backends = (SearchFilter, filters.DjangoFilterBackend)
    filterset_class = GroupsInfoFilter
    search_fields = ('name', 'public_description')
    serializer_class = GroupPreviewSerializer

    @action(
        detail=True,
        methods=['GET']
    )
    def photo(self, request, pk=None):
        group = self.get_object()
        if not group.photo:
            raise Http404()
        return HttpResponseRedirect(redirect_to=group.photo.url)


class GroupViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        RetrieveConversationMixin,
        GenericViewSet,
):
    """
    Your groups: list, create, update
    """
    queryset = GroupModel.objects
    filter_backends = (SearchFilter, filters.DjangoFilterBackend)
    filterset_class = GroupsFilter
    search_fields = ('name', 'public_description')
    serializer_class = GroupDetailSerializer
    permission_classes = (IsAuthenticated, IsGroupEditor)

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
        qs = self.queryset

        if self.action in ('retrieve', 'list'):
            qs = qs.annotate_active_editors_count().annotate_yesterdays_member_count().prefetch_related(
                'members',
                'groupmembership_set',
                'groupmembership_set__trusted_by',
            )

        if self.action != 'join':
            qs = qs.filter(members=self.request.user)

        return qs

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
        self.check_permissions(request)
        membership = get_object_or_404(GroupMembership.objects, group=pk, user=request.user)
        membership.lastseen_at = timezone.now()
        if membership.inactive_at is not None:
            stats.member_returned(membership)
        membership.inactive_at = None
        membership.removal_notification_at = None
        membership.save()
        stats.group_activity(membership.group)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['POST'],
        permission_classes=(IsAuthenticated, IsOtherUser),
        url_name='trust-user',
        url_path='users/(?P<user_id>[^/.]+)/trust',
        serializer_class=EmptySerializer
    )
    def trust_user(self, request, pk, user_id):
        """trust the user in a group"""
        self.check_permissions(request)
        membership = get_object_or_404(GroupMembership.objects, group=pk, user=user_id)
        self.check_object_permissions(request, membership)

        trust, created = Trust.objects.get_or_create(
            membership=membership,
            given_by=self.request.user,
        )
        if not created:
            raise ValidationError(_('You already gave trust to this user'))

        return Response(data={})

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
        self.check_permissions(request)
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


class AgreementViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
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
