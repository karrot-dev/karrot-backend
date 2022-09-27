from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from karrot.agreements.serializers import AgreementSerializer
from karrot.agreements.models import Agreement, AgreementProposal
from karrot.conversations.api import RetrieveConversationMixin
from karrot.utils.mixins import PartialUpdateModelMixin


class AgreementPagination(CursorPagination):
    page_size = 20
    max_page_size = 1200
    page_size_query_param = 'page_size'
    ordering = '-id'


class AgreementViewSet(
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    serializer_class = AgreementSerializer
    queryset = Agreement.objects
    filter_backends = (filters.DjangoFilterBackend, )
    permission_classes = (IsAuthenticated, )
    pagination_class = AgreementPagination

    def get_queryset(self):
        qs = self.queryset

        # only for groups current user is a member of
        qs = qs.filter(group__members=self.request.user)

        # only agreements that are currently valid
        qs = qs.filter(valid_from__lte=timezone.now())
        qs = qs.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=timezone.now()))

        return qs


class AgreementProposalViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        PartialUpdateModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    serializer_class = AgreementSerializer
    queryset = AgreementProposal.objects
    filter_backends = (filters.DjangoFilterBackend, )
    permission_classes = (IsAuthenticated, )
    pagination_class = AgreementPagination

    def get_queryset(self):
        qs = self.queryset

        # only for groups current user is a member of
        qs = qs.filter(group__members=self.request.user)

        # only proposes still open
        qs = qs.filter(ends_at__gt=timezone.now())

        return qs

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this agreement"""
        return self.retrieve_conversation(request, pk)
