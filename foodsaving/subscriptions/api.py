from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from foodsaving.subscriptions.models import PushSubscription
from foodsaving.subscriptions.serializers import PushSubscriptionSerializer


class PushSubscriptionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet
):
    """
    PushSubscriptions
    """
    queryset = PushSubscription.objects
    serializer_class = PushSubscriptionSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
