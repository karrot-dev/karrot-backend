from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Concat
from django_filters import IsoDateTimeFromToRangeFilter
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, ModelChoiceFilter, ModelMultipleChoiceFilter
from rest_framework import status, views
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from karrot.activities.models import ActivityType
from karrot.history.models import History, HistoryTypus
from karrot.places.models import Place
from karrot.stats import stats
from karrot.stats.serializers import ActivityHistoryStatsSerializer, FrontendStatsSerializer


class StatsThrottle(UserRateThrottle):
    rate = "60/minute"


def groups_queryset(request):
    return request.user.groups.all()


def users_queryset(request):
    return get_user_model().objects.filter(groups__in=request.user.groups.all())


def activity_type_queryset(request):
    return ActivityType.objects.filter(group__in=request.user.groups.all())


class NonAggregatingCount(Count):
    """A COUNT that does not trigger a GROUP BY to be added

    This is useful when using Subquery in an annotation
    """

    contains_aggregate = False


class NonAggregatingSum(Sum):
    """A SUM that does not trigger a GROUP BY to be added

    This is useful when using Subquery in an annotation
    """

    contains_aggregate = False


class ActivityHistoryStatsFilter(FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    user = ModelMultipleChoiceFilter(queryset=users_queryset, field_name="users")
    date = IsoDateTimeFromToRangeFilter(field_name="activity__date__startswith")
    activity_type = ModelChoiceFilter(queryset=activity_type_queryset, field_name="activity__activity_type")

    class Meta:
        model = History
        fields = ["group", "activity_type", "user"]


class ActivityHistoryStatsViewSet(GenericViewSet):
    serializer_class = ActivityHistoryStatsSerializer
    queryset = History.objects
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ActivityHistoryStatsFilter
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_entries(), many=True)
        return Response(serializer.data)

    def get_entries(self):
        # ActivityHistoryStatsFilter will validate and use these params
        # for History queryset filtering, but we also want them for other purposes
        user_id = self.request.query_params.get("user", None)
        group_id = self.request.query_params.get("group", None)

        # our main history queryset, which contains all the filter params
        # remove the ordering as it's not important and breaks some sub queries
        history_qs = (
            super()
            .filter_queryset(self.queryset)
            .filter(
                place=OuterRef("id"),
                # there are some old null entries in the db
                # just ignore them, making it consistent with
                # how stats always worked
                activity__isnull=False,
            )
            .order_by()
        )

        feedback_filter = Q(typus=HistoryTypus.ACTIVITY_DONE)

        if user_id:
            feedback_filter &= Q(activity__feedback__given_by=user_id)

        # these are activities missed by anyone
        # which is used to match up with activities that people left
        all_missed_activities = History.objects.filter(typus=HistoryTypus.ACTIVITY_MISSED).values_list("activity")

        done_count = (
            history_qs.filter(typus=HistoryTypus.ACTIVITY_DONE)
            .annotate(count=NonAggregatingCount("id"))
            .values("count")
        )

        missed_count = (
            history_qs.filter(typus=HistoryTypus.ACTIVITY_MISSED)
            .annotate(count=NonAggregatingCount("id"))
            .values("count")
        )

        no_show_count = (
            history_qs.filter(typus=HistoryTypus.ACTIVITY_DONE)
            .filter(
                Q(activity__feedback__no_shows__user=user_id)
                if user_id
                # Important to include this isnull=False condition when we don't have a user,
                # or django will use a LEFT OUTER JOIN and the query will have a count of 1
                else Q(activity__feedback__no_shows__user__isnull=False)
            )
            .annotate(
                count=NonAggregatingCount(
                    # Needs to be counted per activity+user combo
                    # Each activity could have multiple no_show reports for a given user
                    # But we want to only count per activity
                    # We use the concat to make something unique per activity/user combo to use in our distinct clause
                    Concat("activity", Value("|"), "activity__feedback__no_shows__user"),
                    distinct=True,
                )
            )
            .values("count")
        )

        # you can have many leaves for the same activity, but
        # we only want to count it per unique activity+user
        # (activity leaves only ever have one user, so users is always one item)
        leave_count_annotation = NonAggregatingCount(
            Concat("activity", Value("|"), "users"),
            distinct=True,
        )

        leave_count = (
            history_qs.filter(typus=HistoryTypus.ACTIVITY_LEAVE).annotate(count=leave_count_annotation).values("count")
        )

        leave_late_count = (
            history_qs.add_activity_left_late(hours=settings.ACTIVITY_LEAVE_LATE_HOURS)
            .filter(activity_left_late=True)
            .annotate(count=leave_count_annotation)
            .values("count")
        )

        leave_missed_count = (
            history_qs.filter(
                typus=HistoryTypus.ACTIVITY_LEAVE,
                activity__in=all_missed_activities,
            )
            .annotate(count=leave_count_annotation)
            .values("count")
        )

        leave_missed_late_count = (
            history_qs.add_activity_left_late(hours=settings.ACTIVITY_LEAVE_LATE_HOURS)
            .filter(
                activity_left_late=True,
                activity__in=all_missed_activities,
            )
            .annotate(count=leave_count_annotation)
            .values("count")
        )

        feedback_count = (
            history_qs.filter(feedback_filter)
            .annotate(feedback_count=NonAggregatingCount("activity__feedback"))
            .values("feedback_count")
        )

        feedback_weight = (
            history_qs.filter(feedback_filter)
            .annotate(feedback_weight=NonAggregatingSum("activity__feedback__weight"))
            .values("feedback_weight")
        )

        return (
            Place.objects.filter(group=group_id)
            .values("group", place=F("id"))
            .annotate(
                done_count=Subquery(done_count),
                missed_count=Subquery(missed_count),
                no_show_count=Subquery(no_show_count),
                leave_count=Subquery(leave_count),
                leave_late_count=Subquery(leave_late_count),
                leave_missed_count=Subquery(leave_missed_count),
                leave_missed_late_count=Subquery(leave_missed_late_count),
                feedback_count=Subquery(feedback_count),
                feedback_weight=Coalesce(Subquery(feedback_weight), 0.0),
            )
            .filter(
                # don't need to check the leave_missed_* ones here, as the leave_* ones will be >0 in those cases
                # TODO: in the query it looks like it's duplicating the filtering stuff from the annotations
                # (which might be fine)
                Q(done_count__gt=0)
                | Q(missed_count__gt=0)
                | Q(leave_count__gt=0)
                | Q(leave_late_count__gt=0)
                | Q(feedback_count__gt=0)
                | Q(feedback_weight__gt=0)
            )
            .order_by("name")
        )


class FrontendStatsView(views.APIView):
    throttle_classes = [StatsThrottle]
    parser_classes = [JSONParser]
    serializer_class = FrontendStatsSerializer  # for OpenAPI generation with drf-spectacular

    @staticmethod
    def post(request, **kwargs):
        serializer = FrontendStatsSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            stats.received_stats(serializer.data["stats"])
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)
