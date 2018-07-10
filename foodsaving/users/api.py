from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import mixins
from rest_framework.decorators import detail_route
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.conversations.api import RetrievePrivateConversationMixin
from foodsaving.users.serializers import UserSerializer, UserInfoSerializer


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    RetrievePrivateConversationMixin,
    GenericViewSet
):
    """
    User Profiles
    """
    queryset = get_user_model().objects.active()
    serializer_class = UserSerializer
    filter_backends = (filters.SearchFilter,)
    permission_classes = (IsAuthenticated,)
    search_fields = ('display_name',)
    filter_fields = ('conversation', 'groups')

    def retrieve(self, request, *args, **kwargs):
        """Get one user profile"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List all accessible users

        # Query parameters
        - `?search` - search in `display_name`
        """
        return super().list(request, *args, **kwargs)

    @detail_route()
    def conversation(self, request, pk=None):
        """Get private conversation with this user"""
        return self.retrieve_private_conversation(request, pk)

    def get_queryset(self):
        users_groups = self.request.user.groups.values('id')
        return self.queryset.filter(Q(groups__in=users_groups) | Q(id=self.request.user.id)).distinct()


class UserPagination(CursorPagination):
    page_size = 2
    ordering = 'id'


class UserInfoViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    Public User Profiles
    """
    queryset = get_user_model().objects.active()
    serializer_class = UserInfoSerializer
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    permission_classes = (IsAuthenticated,)
    search_fields = ('display_name',)
    filter_fields = ('conversation', 'groups')
    pagination_class = UserPagination

