from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.cases.models import Case, Vote
from foodsaving.cases.serializers import CasesSerializer, VoteSerializer
from foodsaving.conversations.api import RetrieveConversationMixin


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
