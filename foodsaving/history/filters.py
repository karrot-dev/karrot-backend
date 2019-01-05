from django_filters import rest_framework as filters

from foodsaving.base.filters import ISODateTimeFromToRangeFilter
from foodsaving.history.models import HistoryTypus, History


def filter_history_typus(qs, field, value):
    return qs.filter(**{field: getattr(HistoryTypus, value)})


class HistoryFilter(filters.FilterSet):
    typus = filters.ChoiceFilter(choices=HistoryTypus.items(), method=filter_history_typus)
    date = ISODateTimeFromToRangeFilter(field_name='date')

    class Meta:
        model = History
        fields = ('group', 'place', 'users', 'typus', 'date', 'series', 'pickup')
