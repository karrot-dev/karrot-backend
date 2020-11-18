from rest_framework import views, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from karrot.status.helpers import status_data, \
    StatusSerializer


class StatusView(views.APIView):
    permission_classes = (IsAuthenticated, )

    @staticmethod
    def get(request, **kwargs):
        return Response(data=StatusSerializer(status_data(request.user)).data, status=status.HTTP_200_OK)
