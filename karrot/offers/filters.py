from django_filters import rest_framework as filters

from karrot.offers.models import Offer


class OffersFilter(filters.FilterSet):
    is_archived = filters.BooleanFilter(method='filter_is_archived')

    class Meta:
        model = Offer
        fields = ('group', )

    def filter_is_archived(self, qs, name, value):
        if value is True:
            return qs.filter(archived_at__isnull=False)
        elif value is False:
            return qs.filter(archived_at__isnull=True)
        return qs
