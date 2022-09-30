from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters, ModelChoiceFilter


def groups_queryset(request):
    return request.user.groups.all()


def filter_active(qs, name, value):
    if value is True:
        # agreements that are currently active
        qs = qs.filter(active_from__lte=timezone.now())
        qs = qs.filter(Q(active_to__isnull=True) | Q(active_to__gte=timezone.now()))
    elif value is False:
        # agreements that are not currently active
        qs = qs.filter(Q(active_from__gte=timezone.now()) | Q(active_to__lte=timezone.now()))
    return qs


def filter_review_due(qs, name, value):
    if value is True:
        qs = qs.filter(review_at__lte=timezone.now())
    return qs


class AgreementFilter(filters.FilterSet):
    group = ModelChoiceFilter(queryset=groups_queryset)
    active = filters.BooleanFilter(method=filter_active)
    review_due = filters.BooleanFilter(method=filter_review_due)
