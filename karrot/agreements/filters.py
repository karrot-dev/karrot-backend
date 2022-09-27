from django_filters import rest_framework as filters, ModelChoiceFilter

from karrot.agreements.models import Agreement


def groups_queryset(request):
    return request.user.groups.all()


class ActivityTypeFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)

    class Meta:
        model = Agreement
        fields = ['group']
