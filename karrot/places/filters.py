from django_filters import rest_framework as filters, ModelChoiceFilter

from karrot.places.models import PlaceType, PlaceStatus


def groups_queryset(request):
    return request.user.groups.all()


class PlaceTypeFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = PlaceType
        fields = ['group']


class PlaceStatusFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = PlaceStatus
        fields = ['group']
