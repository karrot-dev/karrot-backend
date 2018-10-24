from django_filters import rest_framework as filters

from foodsaving.groups.models import Group


def include_empty(qs, name, value):
    if value:
        return qs
    return qs.exclude(members=None)


class GroupsInfoFilter(filters.FilterSet):
    include_empty = filters.BooleanFilter(field_name='members', method=include_empty)

    class Meta:
        model = Group
        fields = ['members', 'include_empty', 'name']


class GroupsFilter(filters.FilterSet):
    class Meta:
        model = Group
        fields = ['members', 'name']
