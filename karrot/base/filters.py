from django import forms
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_str
from django_filters import rest_framework as filters
from django_filters.fields import RangeField

from karrot.base.base_models import CustomDateTimeTZRange


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


class ISODateTimeRangeFromToRangeFilter(filters.Filter):
    """
    Filters a date time *range* field for a date time range

    You probably want to use it with an 'overlap' lookup, e.g.

        date = ISODateTimeRangeFromToRangeFilter(field_name='date', lookup_expr='overlap')

    See https://docs.djangoproject.com/en/2.1/ref/contrib/postgres/fields/#containment-functions
    """

    field_class = DateTimeRangeField

    def filter(self, qs, value):
        if value:
            value = CustomDateTimeTZRange(value.start, value.stop)
        return super().filter(qs, value)
