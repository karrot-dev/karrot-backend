from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from karrot.offers.models import Offer
from karrot.offers.serializers import OfferSerializer
from karrot.utils.mixins import PartialUpdateModelMixin


class OfferViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = OfferSerializer
    queryset = Offer.objects
