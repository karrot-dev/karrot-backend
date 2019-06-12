from django_filters import rest_framework as filters

from karrot.base.filters import ISODateTimeRangeFromToRangeFilter
from karrot.pickups.models import PickupDate, PickupDateSeries, Feedback


class PickupDateSeriesFilter(filters.FilterSet):
    class Meta:
        model = PickupDateSeries
        fields = [
            'place',
        ]


class PickupDatesFilter(filters.FilterSet):
    place = filters.NumberFilter(field_name='place')
    group = filters.NumberFilter(field_name='place__group')
    date = ISODateTimeRangeFromToRangeFilter(field_name='date', lookup_expr='overlap')
    feedback_possible = filters.BooleanFilter(method='filter_feedback_possible')

    class Meta:
        model = PickupDate
        fields = ['place', 'group', 'date', 'series', 'feedback_possible']

    def filter_feedback_possible(self, qs, name, value):
        if value is True:
            return qs.only_feedback_possible(self.request.user)
        return qs.exclude_feedback_possible(self.request.user)


class FeedbackFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name='about__place__group')
    place = filters.NumberFilter(field_name='about__place')
    about = filters.NumberFilter(field_name='about')
    given_by = filters.NumberFilter(field_name='given_by')
    created_at = filters.IsoDateTimeFromToRangeFilter(field_name='created_at')

    class Meta:
        model = Feedback
        fields = ['group', 'place', 'about', 'given_by', 'created_at']
