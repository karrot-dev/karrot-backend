from django_filters import rest_framework as filters

from karrot.history.models import HistoryTypus, History


class HistoryTypusFilter(filters.MultipleChoiceFilter):
    always_filter = False

    def get_filter_predicate(self, v):
        return {self.field_name: getattr(HistoryTypus, v)}


class HistoryFilter(filters.FilterSet):
    typus = HistoryTypusFilter(choices=HistoryTypus.items())
    type = HistoryTypusFilter(choices=HistoryTypus.items(), field_name='typus')
    date = filters.IsoDateTimeFromToRangeFilter(field_name='date')

    class Meta:
        model = History
        fields = ('group', 'place', 'users', 'typus', 'type', 'date', 'series', 'pickup')
