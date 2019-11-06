import json

import glom
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.viewsets import GenericViewSet

from karrot.conversations.api import RetrieveConversationMixin
from karrot.offers.models import Offer
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
    pagination_class = OfferPagination
    parser_classes = [JSONWithFilesMultiPartParser, JSONParser]

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user).distinct()

    @action(
        detail=True,
    )
    def conversation(self, request, pk=None):
        """Get conversation ID of this application"""
        return self.retrieve_conversation(request, pk)
