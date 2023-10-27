from django_filters import rest_framework as filters

from karrot.offers.models import Offer


class OffersFilter(filters.FilterSet):
    # for legacy API support
    status = filters.ChoiceFilter(
        method='filter_status', choices=[(val, val) for val in (
            'active',
            'archived',
        )]
    )

    class Meta:
        model = Offer
        fields = ('group', )

    def filter_status(self, qs, name, value):
        if value == 'active':
            return qs.filter(archived_at__isnull=True)
        elif value == 'archived':
            return qs.filter(archived_at__isnull=False)
        return qs
