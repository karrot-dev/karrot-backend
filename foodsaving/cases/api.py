from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import GenericViewSet

from foodsaving.cases import stats
from foodsaving.cases.models import GroupCase, Vote
from foodsaving.cases.serializers import ConflictResolutionSerializer, VoteSerializer
from foodsaving.conversations.api import RetrieveConversationMixin


class IsOngoing(BasePermission):
    message = _('Cannot only modify vote for ongoing cases')

    def has_object_permission(self, request, view, obj):
        return obj.is_ongoing()


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
    queryset = GroupCase.objects
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
        return super().get_queryset().filter(participants=self.request.user).prefetch_stuff(user=self.request.user)

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this case"""
        return self.retrieve_conversation(request, pk)

    @action(
        detail=True,
        methods=['POST', 'DELETE'],
        serializer_class=VoteSerializer,
        permission_classes=(IsAuthenticated, IsOngoing)
    )
    def vote(self, request, **kwargs):
        self.check_permissions(request)
        case = self.get_object()
        self.check_object_permissions(request, case)

        voting = case.latest_voting()
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
