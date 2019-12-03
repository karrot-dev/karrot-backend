from rest_framework import views, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from karrot.stats import stats
from karrot.stats.serializers import StatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = '60/minute'


class StatsView(views.APIView):
    throttle_classes = [StatsThrottle]
    parser_classes = [JSONParser]

    @staticmethod
    def post(request, **kwargs):
        serializer = StatsSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            stats.received_stats(serializer.data['stats'])
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
