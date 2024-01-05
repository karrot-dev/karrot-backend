from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.serializers import WebPushSubscribeSerializer, WebPushUnsubscribeSerializer


class WebPushSubscriptionViewSet(GenericViewSet):
    """
    WebPushSubscriptions
    """

    queryset = WebPushSubscription.objects
    serializer_class = WebPushSubscribeSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @action(
        detail=False,
        methods=["POST"],
        serializer_class=WebPushSubscribeSerializer,
    )
    def subscribe(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # don't want duplicate push notifications for this endpoint/key combo
        self.get_queryset().filter(
            endpoint=request.data["endpoint"],
            keys__contains=request.data["keys"],
        ).delete()

        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["POST"],
        serializer_class=WebPushUnsubscribeSerializer,
    )
    def unsubscribe(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # we could have ended up with multiple, so delete them all
        self.get_queryset().filter(
            endpoint=serializer.data["endpoint"],
            keys__contains=serializer.data["keys"],
        ).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
