from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django_filters import IsoDateTimeFromToRangeFilter
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, ModelChoiceFilter
from rest_framework import views, status
from rest_framework.mixins import ListModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from karrot.activities.models import Activity
from karrot.history.models import HistoryTypus, History
from karrot.stats import stats
from karrot.stats.serializers import FrontendStatsSerializer, ActivityHistoryStatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = '60/minute'


def groups_queryset(request):
    return request.user.groups.all()


def users_queryset(request):
    return get_user_model().objects.filter(groups__in=request.user.groups.all())


def history_filter_user(qs, name, value):
    if value:
        qs = qs.filter(users__in=[value])
    return qs


class ActivityHistoryStatsFilter(FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    user = ModelChoiceFilter(queryset=users_queryset, method=history_filter_user)
    date = IsoDateTimeFromToRangeFilter(field_name='activity__date__startswith')

    class Meta:
        model = History
        fields = ['group', 'user']


class ActivityHistoryStatsViewSet(ListModelMixin, GenericViewSet):
    serializer_class = ActivityHistoryStatsSerializer
    queryset = History.objects
    filter_backends = (DjangoFilterBackend, )
    filterset_class = ActivityHistoryStatsFilter
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        user_id = self.request.query_params.get('user', None)

        feedback_weight_filter = Q(typus=HistoryTypus.ACTIVITY_DONE)

        if user_id:
            feedback_weight_filter &= Q(activity__feedback__given_by=user_id)

        return self.filter_queryset(super().get_queryset()) \
            .annotate_activity_leave_seconds() \
            .values('place', 'group') \
            .filter(typus__in=[
                HistoryTypus.ACTIVITY_DONE,
                HistoryTypus.ACTIVITY_LEAVE,
            ]) \
            .annotate(
                done_count=Count('activity', filter=Q(
                    typus=HistoryTypus.ACTIVITY_DONE,
                )),
                leave_count=Count('activity', filter=Q(
                    typus=HistoryTypus.ACTIVITY_LEAVE,
                    activity__in=Activity.objects.done_not_full(),
                )),
                leave_late_count=Count('activity', filter=Q(
                    typus=HistoryTypus.ACTIVITY_LEAVE,
                    activity__in=Activity.objects.done_not_full(),
                    activity_leave_seconds__lte=timedelta(hours=settings.ACTIVITY_LEAVE_LATE_HOURS).total_seconds()),
                ),
                feedback_weight=Coalesce(Sum('activity__feedback__weight', filter=feedback_weight_filter), 0)) \
            .filter(
                Q(done_count__gt=0) | Q(leave_count__gt=0) | Q(leave_late_count__gt=0) | Q(feedback_weight__gt=0)) \
            .order_by('place__name')


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
