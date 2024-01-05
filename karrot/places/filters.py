from django_filters import ModelChoiceFilter
from django_filters import rest_framework as filters

from karrot.places.models import PlaceStatus, PlaceType


def groups_queryset(request):
    return request.user.groups.all()


class PlaceTypeFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = PlaceType
        fields = ["group"]


class PlaceStatusFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = PlaceStatus
        fields = ["group"]
