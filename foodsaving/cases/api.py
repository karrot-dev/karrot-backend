from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from foodsaving.cases import stats
from foodsaving.cases.models import Case, Vote, Voting
from foodsaving.cases.serializers import ConflictResolutionSerializer, VoteSerializer
from foodsaving.conversations.api import RetrieveConversationMixin
from foodsaving.groups.models import Group


class IsNotExpired(BasePermission):
    message = _('Cannot modify expired votings')

    def has_object_permission(self, request, view, obj):
        return not obj.is_expired()


class ConflictResolutionThrottle(UserRateThrottle):
    rate = '10/day'


class CasesPagination(CursorPagination):
    page_size = 10
    ordering = 'id'


class ConflictResolutionsViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        mixins.ListModelMixin,
        RetrieveConversationMixin,
        GenericViewSet,
):
    queryset = Case.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_fields = ('group', 'status')
    serializer_class = ConflictResolutionSerializer
    permission_classes = (IsAuthenticated, )
    pagination_class = CasesPagination

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_classes = (ConflictResolutionThrottle, )
        return super().get_throttles()

    def get_queryset(self):
        groups = Group.objects.user_is_editor(self.request.user)
        return super().get_queryset().filter(group__in=groups)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this case"""
        return self.retrieve_conversation(request, pk)

    @action(
        detail=False,
        methods=['POST', 'DELETE'],
        url_name='vote-case',
        url_path='votings/(?P<voting_id>[^/.]+)/vote',
        serializer_class=VoteSerializer,
        permission_classes=(IsAuthenticated, IsNotExpired)
    )
    def vote(self, request, voting_id):
        self.check_permissions(request)
        cases = self.get_queryset()
        queryset = Voting.objects.filter(case__in=cases)
        voting = get_object_or_404(queryset, id=voting_id)
        self.check_object_permissions(request, voting)

        vote_qs = Vote.objects.filter(option__voting=voting, user=request.user)

        if request.method == 'POST':
            instances = vote_qs.all()
            context = self.get_serializer_context()
            context['voting'] = voting
            serializer = VoteSerializer(data=request.data, instance=instances, many=True, context=context)
            serializer.is_valid(raise_exception=True)
            instances = serializer.save()

            # somehow serializer.data is empty, we need to re-serialize...
            serializer = VoteSerializer(instance=instances, many=True)
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)

        if request.method == 'DELETE':
            deleted_rows, _ = vote_qs.delete()
            deleted = deleted_rows > 0

            if deleted:
                stats.vote_deleted(voting.case)

            return Response(
                data={},
                status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND,
            )
