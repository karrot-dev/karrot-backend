from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters, ModelChoiceFilter


def groups_queryset(request):
    return request.user.groups.all()


def filter_active(qs, name, value):
    if value is True:
        # agreements that are currently valid
        qs = qs.filter(active_from__lte=timezone.now())
        qs = qs.filter(Q(active_until__isnull=True) | Q(active_until__gte=timezone.now()))
    elif value is False:
        # agreements that are not currently valid
        qs = qs.filter(Q(active_from__gte=timezone.now()) | Q(active_until__lte=timezone.now()))
    return qs


class AgreementFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    active = filters.BooleanFilter(method=filter_active)
