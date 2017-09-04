import django_filters
from django import forms
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_str
from django_filters.fields import RangeField
from django_filters.rest_framework import filters, FilterSet

from foodsaving.activity.models import ActivityTypus, Activity


class ISODateTimeField(forms.DateTimeField):
    def strptime(self, value, format):
        return parse_datetime(force_str(value))


class DateTimeRangeField(RangeField):
    def __init__(self, *args, **kwargs):
        fields = (
            ISODateTimeField(),
            ISODateTimeField())
        super(DateTimeRangeField, self).__init__(fields, *args, **kwargs)


class DateTimeFromToRangeFilter(django_filters.RangeFilter):
    field_class = DateTimeRangeField


def filter_activity_typus(qs, field, value):
    return qs.filter(**{field: getattr(ActivityTypus, value)})


class ActivityFilter(FilterSet):
    typus = filters.ChoiceFilter(choices=ActivityTypus.items(), method=filter_activity_typus)
    date = DateTimeFromToRangeFilter(name='date')

    class Meta:
        model = Activity
        fields = ('group', 'store', 'users', 'typus', 'date')

