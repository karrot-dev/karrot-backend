from rest_framework import views, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from karrot.unsubscribe.serializers import UnsubscribeSerializer


class UnsubscribeView(views.APIView):
    permission_classes = (AllowAny, )

    @staticmethod
    def post(request, token):
        """
        Receive unauthenticated but signed unsubscribe requests
        These are the things people can click in emails regardless of whether they are logged in
        """
        serializer = UnsubscribeSerializer(data={'token': token, **request.data})
        if serializer.is_valid():
            serializer.save()
            return Response({}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
