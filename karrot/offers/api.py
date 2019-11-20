import json

import glom
from django.db.models import Q
from django.http import HttpResponseRedirect, Http404
from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrieveConversationMixin
from karrot.offers.models import Offer, OfferImage, OfferStatus
from karrot.offers.serializers import OfferSerializer
from karrot.utils.mixins import PartialUpdateModelMixin


class OfferPagination(CursorPagination):
    page_size = 20
    ordering = '-created_at'


class JSONWithFilesMultiPartParser(MultiPartParser):
    """"
    A multipart parser that allows you send JSON with files to be nested inside it

    So, if you you had an model with a name and image field you kind of want to be able to
    update it with:

        {
            "name": "foo",
            "image": <an uploaded file>
        }

    ... but of course you can't do that in JSON. You could base64 the content, but that
    makes a HUGE JSON file ...

    This is another way!

    You can send a multipart body with:
    - application/json part for the main document
    - any number of non-JSON parts along with a path into the object for where it should go

    In the above example it would be like this:

        JSON part:
            {
                "name": "foo",
            }
        "image" part:
            <some binary content for the image>

    OR, as you have to do in client JS:

        const document = { name: "foo" }
        const imageBlob = getImageBlobFromWhereever()
        const data = new FormData()
        data.append(
          'document',
          new Blob(
            [JSON.stringify(document)],
            { type: 'application/json' },
          )
        )
        data.append('image', imageBlob, 'image.jpg')

    """
    def parse(self, stream, media_type=None, parser_context=None):
        data = {}
        parsed = MultiPartParser.parse(self, stream, media_type, parser_context)

        # Find any JSON content first
        for name, content in parsed.files.items():
            if content.content_type != 'application/json':
                continue
            data.update(**json.load(content.file))

        # Now get any other content
        for name, content in parsed.files.items():
            if content.content_type == 'application/json':
                continue
            # name is the path into the object to assign
            glom.assign(data, name, content)

        return data


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
        return self.queryset.filter(
            Q(group__members=self.request.user),
            Q(user=self.request.user) | Q(status=OfferStatus.ACTIVE.value),
        ).distinct()

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
    def accept(self, request, pk=None):
        self.check_permissions(request)
        offer = self.get_object()
        self.check_object_permissions(request, offer)
        if offer.status != OfferStatus.ACTIVE.value:
            raise ValidationError(_('You can only accept an active offer'))
        offer.accept()
        serializer = self.get_serializer(offer)
        return Response(data=serializer.data)

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
