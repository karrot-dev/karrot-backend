from django_filters import ModelChoiceFilter
from django_filters import rest_framework as filters

from karrot.places.models import PlaceType


def groups_queryset(request):
    return request.user.groups.all()


class PlaceTypeFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = PlaceType
        fields = ["group"]
