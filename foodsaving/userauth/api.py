from django.contrib.auth import logout, update_session_auth_hash
from django.middleware.csrf import get_token as generate_csrf_token_for_frontend
from django.utils import timezone
from rest_framework import status, generics, views
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from foodsaving.userauth.serializers import AuthLoginSerializer, AuthUserSerializer, VerifyMailSerializer, \
    ChangePasswordSerializer, RequestResetPasswordSerializer, ResetPasswordSerializer, ChangeMailSerializer
from foodsaving.userauth.permissions import MailIsNotVerified


class LogoutView(views.APIView):
    def post(self, request, **kwargs):
        """ Log out """
        logout(request)
        return Response(status=status.HTTP_200_OK, data={})


class AuthView(generics.GenericAPIView):
    serializer_class = AuthLoginSerializer

    def post(self, request, **kwargs):
        """ Log in """
        serializer = AuthLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            return Response(data=AuthUserSerializer(request.user).data, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AuthUserView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AuthUserSerializer

    def get_permissions(self):
        # Allow creating user when not logged in
        if self.request.method.lower() == 'post':
            return ()
        return super().get_permissions()

    def post(self, request):
        """Create a new user"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        """Update user profile"""
        serializer = self.get_serializer(request.user, request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get(self, request):
        """Get logged-in user"""
        generate_csrf_token_for_frontend(request)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def delete(self, request):
        """
        Deletes the user from the database

        To keep historic pickup infos, don't delete this user, but remove its details from the database.
        """
        user = request.user
        from foodsaving.groups.models import Group
        from foodsaving.groups.models import GroupMembership

        # Emits pre_delete and post_delete signals, they are used to remove the user from pick-ups
        for _ in Group.objects.filter(members__in=[user, ]):
            GroupMembership.objects.filter(group=_, user=user).delete()

        user.description = ''
        user.set_unusable_password()
        user.mail = None
        user.is_active = False
        user.is_staff = False
        user.mail_verified = False
        user.unverified_email = None
        user.deleted_at = timezone.now()
        user.deleted = True
        user.delete_photo()

        user.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class VerifyMailView(generics.GenericAPIView):
    # No need to add the MailIsNotVerified permission because
    # verification codes only exist for unverified users anyway.
    permission_classes = (AllowAny,)
    serializer_class = VerifyMailSerializer

    def post(self, request):
        """
        Verify an e-mail address.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})


class ResendMailVerificationCodeView(views.APIView):
    permission_classes = (IsAuthenticated, MailIsNotVerified)

    def post(self, request):
        """
        Resend a verification code (via e-mail).
        """
        self.check_object_permissions(request, request.user)
        request.user.send_mail_verification_code()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})


class RequestResetPasswordView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = RequestResetPasswordSerializer

    def post(self, request):
        """
        Request a reset of the password.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})


class ResetPasswordView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        """
        Reset the password using a previously requested verification token.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT, data={})


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        """
        Change the password.
        """
        self.check_object_permissions(request, request.user)
        serializer = self.get_serializer(request.user, request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Keep the user logged in
        update_session_auth_hash(request, user)

        return Response(status=status.HTTP_200_OK, data=AuthUserSerializer(instance=request.user).data)


class ChangeMailView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangeMailSerializer

    def post(self, request):
        """
        Change the e-mail address.
        """
        self.check_object_permissions(request, request.user)
        serializer = self.get_serializer(request.user, request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK, data=AuthUserSerializer(instance=request.user).data)
