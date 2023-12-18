from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from karrot.agreements.permissions import IsGroupEditor
from karrot.agreements.filters import AgreementFilter
from karrot.agreements.serializers import AgreementSerializer
from karrot.agreements.models import Agreement
from karrot.utils.mixins import PartialUpdateModelMixin


class AgreementPagination(CursorPagination):
    page_size = 20
    max_page_size = 1200
    page_size_query_param = "page_size"
    ordering = "-id"


class AgreementViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    PartialUpdateModelMixin,
    GenericViewSet,
):
    serializer_class = AgreementSerializer
    queryset = Agreement.objects
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = AgreementFilter
    permission_classes = (
        IsAuthenticated,
        IsGroupEditor,
    )
    pagination_class = AgreementPagination

    def get_queryset(self):
        qs = self.queryset

        # only for groups current user is a member of
        qs = qs.filter(group__members=self.request.user)

        return qs
