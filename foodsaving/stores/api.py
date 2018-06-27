from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from rest_framework_extensions.etag.mixins import ReadOnlyETAGMixin

from foodsaving.stores.models import Store as StoreModel
from foodsaving.stores.serializers import StoreSerializer
from foodsaving.utils.mixins import PartialUpdateModelMixin


class StoreViewSet(
    ReadOnlyETAGMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    PartialUpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    """
    Stores

    # Query parameters
    - `?group` - filter by store group id
    - `?search` - search in name and description
    """
    serializer_class = StoreSerializer
    queryset = StoreModel.objects.filter(deleted=False)
    filter_fields = ('group', 'name')
    filter_backends = (SearchFilter, DjangoFilterBackend)
    search_fields = ('name', 'description')
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.filter(group__members=self.request.user)
