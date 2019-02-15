from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrievePrivateConversationMixin
from karrot.users.serializers import UserSerializer, UserInfoSerializer, UserProfileSerializer


class UserViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, RetrievePrivateConversationMixin, GenericViewSet):
    """
    User Profiles
    """
    queryset = get_user_model().objects.active()
    serializer_class = UserSerializer
    filter_backends = (filters.SearchFilter, )
    permission_classes = (IsAuthenticated, )
    search_fields = ('display_name', )

    def retrieve(self, request, *args, **kwargs):
        """Get one user profile"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List all accessible users

        # Query parameters
        - `?search` - search in `display_name`
        """
        return super().list(request, *args, **kwargs)

    @action(detail=True, serializer_class=UserProfileSerializer)
    def profile(self, request, pk=None):
        user = self.get_object()
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=True)
    def conversation(self, request, pk=None):
        """Get private conversation with this user"""
        return self.retrieve_private_conversation(request, pk)

    def get_queryset(self):
        is_member_of_group = Q(groups__in=self.request.user.groups.all())

        is_self = Q(id=self.request.user.id)

        groups = self.request.user.groups.all()
        is_applicant_of_group = Q(application__group__in=groups)

        return self.queryset.filter(is_member_of_group | is_applicant_of_group | is_self).distinct()


class UserPagination(CursorPagination):
    page_size = 20
    ordering = 'id'


class UserInfoViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    """
    Public User Profiles (for now only users that share a conversation)
    """
    queryset = get_user_model().objects.active()
    serializer_class = UserInfoSerializer
    permission_classes = (IsAuthenticated, )
    pagination_class = UserPagination

    def get_queryset(self):
        return self.queryset.filter(
            Q(conversation__in=self.request.user.conversation_set.all()) | Q(id=self.request.user.id)
        ).distinct()
