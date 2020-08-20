from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, ModelChoiceFilter
from rest_framework import views, status
from rest_framework.mixins import ListModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from karrot.history.models import HistoryTypus, History
from karrot.places.models import Place
from karrot.stats import stats
from karrot.stats.serializers import FrontendStatsSerializer, PlaceStatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = '60/minute'


def users_queryset(request):
    return get_user_model().objects.filter(groups__in=request.user.groups.all())


class PlaceStatsFilter(FilterSet):
    user = ModelChoiceFilter(queryset=users_queryset, method='filter_user')

    def filter_user(self, qs, name, value):
        return qs.filter(history__users__in=[value]) if value else qs

    class Meta:
        model = Place
        fields = ['user']


class PlaceStatsViewSet(ListModelMixin, GenericViewSet):
    """Statistics per-place"""
    serializer_class = PlaceStatsSerializer
    queryset = Place.objects
    filter_backends = (DjangoFilterBackend, )
    filterset_class = PlaceStatsFilter
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user).annotate(
            activity_join_count=Count('history', filter=Q(history__typus=HistoryTypus.ACTIVITY_JOIN)),
            activity_leave_count=Count('history', filter=Q(history__typus=HistoryTypus.ACTIVITY_LEAVE)),
            activity_leave_late_count=Count(
                'history', filter=Q(history__in=History.objects.activity_left_late(hours=24))
            ),
            activity_done_count=Count('history', filter=Q(history__typus=HistoryTypus.ACTIVITY_DONE)),
            # filter for feedback_as_sum=True as this is possible to calculate here, query gets too hairy otherwise
            # all pickups since 2019-12-26 have this as true...
            activity_feedback_weight=Coalesce(
                Sum('activities__feedback__weight', filter=Q(activities__feedback_as_sum=True)), 0
            ),
        )


class FrontendStatsView(views.APIView):
    throttle_classes = [StatsThrottle]
    parser_classes = [JSONParser]

    @staticmethod
    def post(request, **kwargs):
        serializer = FrontendStatsSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            stats.received_stats(serializer.data['stats'])
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
