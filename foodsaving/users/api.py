from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import filters
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import list_route
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.users.permissions import IsNotVerified
from foodsaving.users.serializers import UserSerializer, VerifyMailSerializer


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    User Profiles
    """
    queryset = get_user_model().objects
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

    @list_route(
        methods=['POST'],
        permission_classes=(IsNotVerified, IsAuthenticated),
        serializer_class=VerifyMailSerializer
    )
    def verify_mail(self, request, pk=None):
        """
        Send token to verify e-mail

        requires "key" parameter
        """
        self.check_object_permissions(request, request.user)
        serializer = self.get_serializer(request.user, request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})

    @list_route(
        methods=['POST'],
    )
    def resend_verification(self, request, pk=None):
        """Resend verification e-mail"""
        if request.user.mail_verified:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={'error': 'Already verified'})
        request.user.send_new_verification_code()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})

    @list_route(
        methods=['POST'],
        permission_classes=(AllowAny,)
    )
    def reset_password(self, request, pk=None):
        """
        Request new password

        send a request with 'email' to this endpoint to get a new password mailed
        """
        request_email = request.data.get('email')
        if not request_email:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={'error': 'mail address is not provided'})
        try:
            user = get_user_model().objects.get(email__iexact=request_email)
        except get_user_model().DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        user.reset_password()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})
