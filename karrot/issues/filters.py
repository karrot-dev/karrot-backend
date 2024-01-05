from django_filters import ModelChoiceFilter, MultipleChoiceFilter
from django_filters import rest_framework as filters

from karrot.issues.models import Issue, IssueStatus


def groups_queryset(request):
    return request.user.groups.all()


class IssuesFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    status = MultipleChoiceFilter(choices=[(status.value, status.value) for status in IssueStatus])

    class Meta:
        model = Issue
        fields = ["group", "status"]
