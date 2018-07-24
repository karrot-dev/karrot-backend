from django import forms
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_str
from django_filters.fields import RangeField
from django_filters.rest_framework import FilterSet, RangeFilter, NumberFilter, BooleanFilter

from foodsaving.base.filters import ISODateTimeFromToRangeFilter
from foodsaving.pickups.models import PickupDate, PickupDateSeries, Feedback


class PickupDateSeriesFilter(FilterSet):
    class Meta:
        model = PickupDateSeries
        fields = [
            'store',
        ]


class PickupDatesFilter(FilterSet):
    store = NumberFilter(field_name='store')
    group = NumberFilter(field_name='store__group__id')
    date = ISODateTimeFromToRangeFilter(field_name='date')
    feedback_possible = BooleanFilter(method='filter_feedback_possible')

    class Meta:
        model = PickupDate
        fields = ['store', 'group', 'date', 'series', 'feedback_possible']

    def filter_feedback_possible(self, qs, name, value):
        if value is True:
            return qs.only_feedback_possible(self.request.user)
        return qs.exclude_feedback_possible(self.request.user)


class FeedbackFilter(FilterSet):
    group = NumberFilter(field_name='about__store__group__id')
    store = NumberFilter(field_name='about__store__id')
    about = NumberFilter(field_name='about')
    given_by = NumberFilter(field_name='given_by')
    created_at = ISODateTimeFromToRangeFilter(field_name='created_at')

    class Meta:
        model = Feedback
        fields = ['group', 'store', 'about', 'given_by', 'created_at']
