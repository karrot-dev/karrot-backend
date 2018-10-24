from django import forms
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_str
from django_filters import rest_framework as filters
from django_filters.fields import RangeField


class ISODateTimeField(forms.DateTimeField):
    def strptime(self, value, format):
        return parse_datetime(force_str(value))


class DateTimeRangeField(RangeField):
    def __init__(self, *args, **kwargs):
        fields = (
            ISODateTimeField(),
            ISODateTimeField(),
        )
        super(DateTimeRangeField, self).__init__(fields, *args, **kwargs)


class ISODateTimeFromToRangeFilter(filters.RangeFilter):
    field_class = DateTimeRangeField
