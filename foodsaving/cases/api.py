from django_filters import rest_framework as filters
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from foodsaving.cases.models import Case, Vote, Option
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
    filterset_fields = ('group', 'is_decided')
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

    @action(
        detail=False,
        methods=['POST', 'DELETE'],
        url_name='vote-option',
        url_path='options/(?P<option_id>[^/.]+)/vote',
        serializer_class=VoteSerializer
    )
    def vote(self, request, option_id):
        self.check_permissions(request)
        cases = self.get_queryset()
        queryset = Option.objects.filter(voting__case__in=cases)
        option = get_object_or_404(queryset, id=option_id)
        self.check_object_permissions(request, option)

        if request.method == 'POST':
            serializer = VoteSerializer(data={
                **request.data,
                'option': option.id,
                'user': request.user.id,
            })
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)

        if request.method == 'DELETE':
            deleted_rows, _ = Vote.objects.filter(option=option, user=request.user).delete()
            return Response(
                data={},
                status=status.HTTP_204_NO_CONTENT if deleted_rows > 0 else status.HTTP_404_NOT_FOUND,
            )
