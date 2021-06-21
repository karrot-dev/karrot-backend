from django_filters import rest_framework as filters
from django.db.models import Q

from karrot.base.filters import ISODateTimeRangeFromToRangeFilter
from karrot.activities.models import Activity, ActivitySeries, Feedback, ActivityType


class ActivityTypeFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name='group')

    class Meta:
        model = ActivityType
        fields = ['group']


class ActivitySeriesFilter(filters.FilterSet):
    class Meta:
        model = ActivitySeries
        fields = [
            'place',
        ]


class ActivitiesFilter(filters.FilterSet):
    place = filters.NumberFilter(field_name='place')
    group = filters.NumberFilter(field_name='place__group')
    date = ISODateTimeRangeFromToRangeFilter(field_name='date', lookup_expr='overlap')
    feedback_possible = filters.BooleanFilter(method='filter_feedback_possible')
    joined = filters.BooleanFilter(method='filter_joined')

    class Meta:
        model = Activity
        fields = ['place', 'group', 'date', 'series', 'feedback_possible', 'joined']

    def filter_feedback_possible(self, qs, name, value):
        if value is True:
            return qs.only_feedback_possible(self.request.user)
        return qs.exclude_feedback_possible(self.request.user)

    def filter_joined(self, qs, name, value):
        if value is True:
            return qs.filter(participants=self.request.user)
        elif value is False:
            return qs.filter(~Q(participants=self.request.user))
        return qs


class FeedbackFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name='about__place__group')
    place = filters.NumberFilter(field_name='about__place')
    about = filters.NumberFilter(field_name='about')
    given_by = filters.NumberFilter(field_name='given_by')
    created_at = filters.IsoDateTimeFromToRangeFilter(field_name='created_at')

    class Meta:
        model = Feedback
        fields = ['group', 'place', 'about', 'given_by', 'created_at']
