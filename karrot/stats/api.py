from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django_filters import IsoDateTimeFromToRangeFilter
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, ModelChoiceFilter, ModelMultipleChoiceFilter
from rest_framework import views, status
from rest_framework.mixins import ListModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from karrot.activities.models import ActivityType
from karrot.history.models import HistoryTypus, History
from karrot.stats import stats
from karrot.stats.serializers import FrontendStatsSerializer, ActivityHistoryStatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = '60/minute'


def groups_queryset(request):
    return request.user.groups.all()


def users_queryset(request):
    return get_user_model().objects.filter(groups__in=request.user.groups.all())


def activity_type_queryset(request):
    return ActivityType.objects.filter(group__in=request.user.groups.all())


class ActivityHistoryStatsFilter(FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    user = ModelMultipleChoiceFilter(queryset=users_queryset, field_name='users')
    date = IsoDateTimeFromToRangeFilter(field_name='activity__date__startswith')
    activity_type = ModelChoiceFilter(queryset=activity_type_queryset, field_name='activity__activity_type')

    class Meta:
        model = History
        fields = ['group', 'activity_type', 'user']


class ActivityHistoryStatsViewSet(ListModelMixin, GenericViewSet):
    serializer_class = ActivityHistoryStatsSerializer
    queryset = History.objects
    filter_backends = (DjangoFilterBackend, )
    filterset_class = ActivityHistoryStatsFilter
    permission_classes = (IsAuthenticated, )

    def get_queryset(self):
        # ActivityHistoryStatsFilter has already used the "user" param
        # to filter the history, but we want to pull it out again for filtering
        # other things too
        user_id = self.request.query_params.get('user', None)

        feedback_filter = Q(typus=HistoryTypus.ACTIVITY_DONE)

        if user_id:
            feedback_filter &= Q(activity__feedback__given_by=user_id)

        # these are activities missed by anyone
        # which is used to match up with activities that people left
        all_missed_activities = History.objects.filter(typus=HistoryTypus.ACTIVITY_MISSED).values_list('activity')

        return self.filter_queryset(super().get_queryset()) \
            .annotate_activity_leave_late(hours=settings.ACTIVITY_LEAVE_LATE_HOURS) \
            .values('place', 'group') \
            .filter(typus__in=[
                HistoryTypus.ACTIVITY_DONE,
                HistoryTypus.ACTIVITY_MISSED,
                HistoryTypus.ACTIVITY_LEAVE,
            ]) \
            .annotate(
                done_count=Count('activity', distinct=True, filter=Q(
                    typus=HistoryTypus.ACTIVITY_DONE,
                )),
                missed_count=Count('activity', distinct=True, filter=Q(
                    typus=HistoryTypus.ACTIVITY_MISSED,
                )),
                leave_count=Count('activity', distinct=True, filter=Q(
                    typus=HistoryTypus.ACTIVITY_LEAVE,
                )),
                leave_late_count=Count('activity', distinct=True, filter=Q(
                    activity_leave_late=True,
                )),
                leave_missed_count=Count('activity', distinct=True, filter=Q(
                    typus=HistoryTypus.ACTIVITY_LEAVE,
                    activity__in=all_missed_activities,
                )),
                leave_missed_late_count=Count('activity', distinct=True, filter=Q(
                    activity_leave_late=True,
                    activity__in=all_missed_activities,
                )),
                feedback_count=Count('activity__feedback', filter=feedback_filter),
                feedback_weight=Coalesce(Sum('activity__feedback__weight', filter=feedback_filter), 0.0)) \
            .filter(
                # don't need to check the leave_missed_* ones here, as the leave_* ones will be >0 in those cases
                Q(done_count__gt=0) |
                Q(missed_count__gt=0) |
                Q(leave_count__gt=0) |
                Q(leave_late_count__gt=0) |
                Q(feedback_count__gt=0) |
                Q(feedback_weight__gt=0)) \
            .order_by('place__name')


class FrontendStatsView(views.APIView):
    throttle_classes = [StatsThrottle]
    parser_classes = [JSONParser]
    serializer_class = FrontendStatsSerializer  # for OpenAPI generation with drf-spectacular

    @staticmethod
    def post(request, **kwargs):
        serializer = FrontendStatsSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            stats.received_stats(serializer.data['stats'])
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
