from django.db.models import Q
from django_filters import ModelChoiceFilter
from django_filters import rest_framework as filters

from karrot.activities.models import Activity, ActivitySeries, ActivityType, Feedback
from karrot.base.filters import ISODateTimeRangeFromToRangeFilter
from karrot.places.models import PlaceStatus


def groups_queryset(request):
    return request.user.groups.all()


class ActivityTypeFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = ActivityType
        fields = ["group"]


class ActivitySeriesFilter(filters.FilterSet):
    class Meta:
        model = ActivitySeries
        fields = [
            "place",
        ]


class PublicActivitiesFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name="place__group")
    date = ISODateTimeRangeFromToRangeFilter(field_name="date", lookup_expr="overlap")


def place_status_queryset(request):
    if request:
        return PlaceStatus.objects.filter(group__members=request.user)
    return PlaceStatus.objects.none()


class ActivitiesFilter(filters.FilterSet):
    place = filters.NumberFilter(field_name="place")
    place_status = filters.ModelChoiceFilter(field_name="place__status", queryset=place_status_queryset)
    place_archived = filters.BooleanFilter(method="filter_place_archived")
    group = filters.NumberFilter(field_name="place__group")
    date = ISODateTimeRangeFromToRangeFilter(field_name="date", lookup_expr="overlap")
    feedback_possible = filters.BooleanFilter(method="filter_feedback_possible")
    has_feedback = filters.BooleanFilter(method="filter_has_feedback")
    joined = filters.BooleanFilter(method="filter_joined")
    activity_type = filters.NumberFilter(field_name="activity_type")
    slots = filters.ChoiceFilter(method="filter_slots", choices=[(val, val) for val in ("free", "empty", "joined")])
    places = filters.ChoiceFilter(method="filter_places", choices=[(val, val) for val in ("subscribed",)])

    class Meta:
        model = Activity
        fields = [
            "place",
            "group",
            "date",
            "series",
            "feedback_possible",
            "joined",
            "activity_type",
            "slots",
            "places",
        ]

    def filter_place_archived(self, qs, name, value):
        if value is True:
            return qs.filter(place__archived_at__isnull=False)
        elif value is False:
            return qs.filter(place__archived_at__isnull=True)
        return qs

    def filter_feedback_possible(self, qs, name, value):
        if value is True:
            return qs.only_feedback_possible(self.request.user)
        elif value is False:
            return qs.exclude_feedback_possible(self.request.user)
        return qs

    def filter_has_feedback(self, qs, name, value):
        if value is True:
            return qs.annotate_feedback_count().filter(feedback_count__gt=0)
        elif value is False:
            return qs.annotate_feedback_count().filter(feedback_count=0)
        return qs

    def filter_joined(self, qs, name, value):
        if value is True:
            return qs.filter(participants=self.request.user)
        elif value is False:
            return qs.filter(~Q(participants=self.request.user))
        return qs

    def filter_slots(self, qs, name, value):
        if value == "free":
            return qs.with_free_slots(self.request.user)
        elif value == "empty":
            return qs.empty()
        elif value == "joined":
            return qs.with_participant(self.request.user)
        return qs

    def filter_places(self, qs, name, value):
        if value == "subscribed":
            return qs.filter(place__subscribers=self.request.user)
        return qs


class FeedbackFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name="about__place__group")
    place = filters.NumberFilter(field_name="about__place")
    about = filters.NumberFilter(field_name="about")
    given_by = filters.NumberFilter(field_name="given_by")
    created_at = filters.IsoDateTimeFromToRangeFilter(field_name="created_at")

    class Meta:
        model = Feedback
        fields = ["group", "place", "about", "given_by", "created_at"]
