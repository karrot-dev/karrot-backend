from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, OuterRef, Q, Subquery, Sum
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

from karrot.activities.models import Activity, Feedback
from karrot.history.models import HistoryTypus, History
from karrot.places.models import Place
from karrot.stats import stats
from karrot.stats.serializers import FrontendStatsSerializer, PlaceStatsSerializer, ActivityHistoryStatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = '60/minute'


def groups_queryset(request):
    return request.user.groups.all()


def users_queryset(request):
    return get_user_model().objects.filter(groups__in=request.user.groups.all())


def filter_user(qs, name, value):
    # we filter the user in the get_queryset method... as it's more complex ...
    # maybe there is a better way to declare the filter field...
    return qs


def filter_date(qs, name, value):
    if value:
        if value.start:
            qs = qs.filter(history__activity__date__startswith__gt=value.start)
    return qs


class PlaceStatsFilter(FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    user = ModelChoiceFilter(queryset=users_queryset, method=filter_user)
    date = IsoDateTimeFromToRangeFilter(field_name='history__activity__date__startswith')

    class Meta:
        model = Place
        fields = ['group', 'user']


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
                HistoryTypus.ACTIVITY_DONE.value,
                HistoryTypus.ACTIVITY_LEAVE.value,
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
                    activity_leave_seconds__lte=timedelta(hours=24).total_seconds()),
                ),
                feedback_weight=Coalesce(Sum('activity__feedback__weight', filter=feedback_weight_filter), 0)) \
            .filter(
                Q(done_count__gt=0) | Q(leave_count__gt=0) | Q(leave_late_count__gt=0) | Q(feedback_weight__gt=0)) \
            .order_by('place__name')


class PlaceStatsViewSet(ListModelMixin, GenericViewSet):
    """Statistics per-place"""
    serializer_class = PlaceStatsSerializer
    queryset = Place.objects
    filter_backends = (DjangoFilterBackend, )
    filterset_class = PlaceStatsFilter
    permission_classes = (IsAuthenticated, )

    # def list(self, request, *args, **kwargs):
    #     queryset = self.filter_queryset(self.get_queryset())
    #     print('--------------  QUERY START  ------------------------')
    #     print(queryset.query)
    #     print('--------------   QUERY END   ------------------------')
    #     serializer = self.get_serializer(queryset, many=True)
    #     return Response(serializer.data)

    def get_queryset(self):
        queryset = self.filter_queryset(super().get_queryset())
        user_id = self.request.query_params.get('user', None)
        date_start = self.request.query_params.get('date_after', None)
        date_end = self.request.query_params.get('date_before', None)

        print('date_start', date_start, type(date_start))
        print('date_end', date_end, type(date_end))

        def count_for(typus, **extra_params):
            filter_params = {'history__typus': typus, **extra_params}
            if user_id:
                filter_params.update({'history__users__in': [user_id]})
            return Count('history', filter=Q(**filter_params))

        def leave_late_count():
            history_queryset = History.objects \
                .activity_left_late(hours=24) \
                .filter(activity__in=Activity.objects.missed())

            if user_id:
                history_queryset = history_queryset.filter(users__in=[user_id])
            return Count('history', filter=Q(history__in=history_queryset))

        feedback_weight_queryset = Feedback.objects \
            .filter(about=OuterRef('history__activity')) \
            .annotate(total_weight=Sum('weight')) \
            .values('total_weight')
        # .filter(about__place=OuterRef('pk')) \
        # .filter(about=OuterRef('history__activity')) \

        if user_id:
            feedback_weight_queryset = feedback_weight_queryset.filter(given_by=user_id)

        queryset = queryset.filter(group__members=self.request.user).annotate(
            activity_done_count=count_for(HistoryTypus.ACTIVITY_DONE),
            activity_leave_count=count_for(
                HistoryTypus.ACTIVITY_LEAVE, history__activity__in=Activity.objects.missed()
            ),
            # activity_leave_late_count=Value(0, output_field=FloatField()),
            activity_leave_late_count=leave_late_count(),
            activity_feedback_weight=Coalesce(Subquery(feedback_weight_queryset), 0),
        ).filter(
            Q(activity_leave_count__gt=0) | Q(activity_leave_late_count__gt=0) | Q(activity_done_count__gt=0) |
            Q(activity_feedback_weight__gt=0)
        )

        print('--------------  QUERY START  ------------------------')
        print(queryset.query)
        print('--------------   QUERY END   ------------------------')

        return queryset


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
