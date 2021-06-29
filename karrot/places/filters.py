from django_filters import rest_framework as filters

from karrot.places.models import PlaceType


class PlaceTypeFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name='group')

    class Meta:
        model = PlaceType
        fields = ['group']
