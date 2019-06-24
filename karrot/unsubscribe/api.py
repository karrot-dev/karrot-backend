from rest_framework import views, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.unsubscribe.serializers import TokenUnsubscribeSerializer, UnsubscribeSerializer


class TokenUnsubscribeView(views.APIView):
    permission_classes = (AllowAny, )

    @staticmethod
    def post(request, token):
        """
        Receive unauthenticated but signed unsubscribe requests
        
        These are the things people can click in emails regardless of whether they are logged in
        """
        serializer = TokenUnsubscribeSerializer(data={'token': token, **request.data})
        if serializer.is_valid():
            serializer.save()
            return Response({}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UnsubscribeViewSet(GenericViewSet):
    permission_classes = (IsAuthenticated, )
    serializer_class = UnsubscribeSerializer

    def create(self, request, **kwargs):
        """
        Receive authenticated unsubscribe requests
        """
        self.check_permissions(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = serializer.save()
        return Response(count)
