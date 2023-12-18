from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from karrot.status.helpers import StatusSerializer, status_data


class StatusView(views.APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = StatusSerializer  # for OpenAPI generation with drf-spectacular

    @staticmethod
    def get(request, **kwargs):
        return Response(data=StatusSerializer(status_data(request.user)).data, status=status.HTTP_200_OK)
