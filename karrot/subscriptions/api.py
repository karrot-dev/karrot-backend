from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from karrot.subscriptions.models import PushSubscription, WebPushSubscription
from karrot.subscriptions.serializers import PushSubscriptionSerializer, CreatePushSubscriptionSerializer, \
    CreateWebPushSubscriptionSerializer, WebPushSubscriptionSerializer


class PushSubscriptionViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                              mixins.DestroyModelMixin, GenericViewSet):
    """
    PushSubscriptions
    """
    queryset = PushSubscription.objects
    serializer_class = PushSubscriptionSerializer
    permission_classes = (IsAuthenticated, )

    def get_serializer_class(self):
        if self.action == 'create':
            return CreatePushSubscriptionSerializer
        return self.serializer_class

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class WebPushSubscriptionViewSet(
        mixins.CreateModelMixin,
        # mixins.ListModelMixin,
        # mixins.RetrieveModelMixin,
        mixins.DestroyModelMixin,
        GenericViewSet,
):
    """
    WebPushSubscriptions
    """
    queryset = WebPushSubscription.objects
    serializer_class = WebPushSubscriptionSerializer
    permission_classes = (IsAuthenticated, )

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateWebPushSubscriptionSerializer
        return self.serializer_class

    def get_object(self):
        print('getting object!')
        return super().get_object()

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
