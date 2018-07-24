from django_filters.rest_framework import filters, FilterSet

from foodsaving.base.filters import ISODateTimeFromToRangeFilter
from foodsaving.history.models import HistoryTypus, History


def filter_history_typus(qs, field, value):
    return qs.filter(**{field: getattr(HistoryTypus, value)})


class HistoryFilter(FilterSet):
    typus = filters.ChoiceFilter(choices=HistoryTypus.items(), method=filter_history_typus)
    date = ISODateTimeFromToRangeFilter(field_name='date')

    class Meta:
        model = History
        fields = ('group', 'store', 'users', 'typus', 'date')
