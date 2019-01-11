from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.cases.models import Case, Vote
from foodsaving.cases.serializers import CasesSerializer, VoteSerializer
from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.groups.models import Group


class CasesPagination(CursorPagination):
    page_size = 10
    ordering = 'id'


class CasesViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        RetrieveConversationMixin,
        GenericViewSet,
):
    queryset = Case.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_fields = ('group', )
    serializer_class = CasesSerializer
    permission_classes = (IsAuthenticated, )
    pagination_class = CasesPagination

    def get_queryset(self):
        groups = Group.objects.user_is_editor(self.request.user)
        return super().get_queryset().filter(group__in=groups)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this case"""
        return self.retrieve_conversation(request, pk)


class VotesViewSet(
        mixins.CreateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
):
    queryset = Vote.objects
    serializer_class = VoteSerializer
    permission_classes = (IsAuthenticated, )
