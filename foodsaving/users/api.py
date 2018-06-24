from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import filters
from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from rest_framework.decorators import detail_route
from rest_framework import status
from rest_framework.response import Response

from foodsaving.users.serializers import UserSerializer


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
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

    def retrieve(self, request, *args, **kwargs):
        """Get one user profile"""
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List all accessible users

        # Query parameters
        - `?search` - search in `display_name`
        """
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        users_groups = self.request.user.groups.values('id')
        return self.queryset.filter(Q(groups__in=users_groups) | Q(id=self.request.user.id)).distinct()

    @detail_route(
        methods=('POST',),
        permission_classes=(IsAuthenticated, )
    )
    def trust(self, request, pk):
        """route for POST /users/{id}/trust/"""
        user = self.get_object()

        # TODO: rate limit
        user.give_trust_by(request.user)

        return Response({}, status=status.HTTP_201_CREATED)
