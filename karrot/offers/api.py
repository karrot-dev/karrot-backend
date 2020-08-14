from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponseRedirect, Http404
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrieveConversationMixin
from karrot.offers import stats
from karrot.offers.models import Offer, OfferImage, OfferStatus
from karrot.offers.serializers import OfferSerializer
from karrot.utils.mixins import PartialUpdateModelMixin
from karrot.utils.parsers import JSONWithFilesMultiPartParser


class OfferPagination(CursorPagination):
    page_size = 20
    ordering = '-created_at'


class IsOfferUser(BasePermission):
    """Is the user the owner of the offer they wish to update?"""

    message = _('You are not the owner of this offer')

    def has_object_permission(self, request, view, offer):
        return request.user == offer.user


class OfferViewSet(
        mixins.CreateModelMixin,
        mixins.RetrieveModelMixin,
        PartialUpdateModelMixin,
        mixins.ListModelMixin,
        GenericViewSet,
        RetrieveConversationMixin,
):
    serializer_class = OfferSerializer
    queryset = Offer.objects
    filter_backends = (filters.DjangoFilterBackend, )
    filterset_fields = (
        'group',
        'status',
    )
    pagination_class = OfferPagination
    parser_classes = [JSONWithFilesMultiPartParser, JSONParser]

    def get_queryset(self):
        qs = self.queryset.filter(group__members=self.request.user)
        is_owner = Q(user=self.request.user)
        is_active = Q(status=OfferStatus.ACTIVE.value)
        if self.action in ('retrieve', 'conversation'):
            # we let people who participated in the conversation retrieve the specific offer and conversation
            ct = ContentType.objects.get_for_model(Offer)
            ids = self.request.user.conversation_set.filter(target_type=ct).values_list('target_id', flat=True)
            qs = qs.filter(is_owner | is_active | Q(id__in=ids))
        else:
            qs = qs.filter(is_owner | is_active)
        return qs.distinct()

    def get_permissions(self):
        if self.action == 'image':
            permission_classes = ()
        elif self.action in ('list', 'retrieve', 'conversation'):
            permission_classes = (IsAuthenticated, )
        else:
            permission_classes = (IsAuthenticated, IsOfferUser)
        return [permission() for permission in permission_classes]

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this offer"""
        return self.retrieve_conversation(request, pk)

    @action(
        detail=True,
        methods=['POST'],
    )
    def archive(self, request, pk=None):
        self.check_permissions(request)
        offer = self.get_object()
        self.check_object_permissions(request, offer)
        if offer.status != OfferStatus.ACTIVE.value:
            raise ValidationError(_('You can only archive an active offer'))
        offer.archive()
        stats.offer_archived(offer)
        serializer = self.get_serializer(offer)
        return Response(data=serializer.data)

    @action(
        detail=True,
        methods=['GET'],
    )
    def image(self, request, pk=None):
        image = OfferImage.objects.filter(offer=pk).first()
        if not image:
            raise Http404()
        return HttpResponseRedirect(redirect_to=image.image.url)
