from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.trust.models import Trust
from foodsaving.trust.serializers import TrustSerializer


class TrustViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              GenericViewSet,):
    queryset = Trust.objects
    serializer_class = TrustSerializer
    permission_classes = (
        IsAuthenticated,
    )
    filter_backends = (DjangoFilterBackend, )
    filter_fields = ('group', 'user', 'given_by')
