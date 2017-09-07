from channels.generic.websockets import JsonWebsocketConsumer
from django.utils import timezone

from foodsaving.subscriptions.models import ChannelSubscription


class Consumer(JsonWebsocketConsumer):
    http_user = True

    def connect(self, message, **kwargs):
        """The user has connected! Register their channel subscription."""
        user = message.user
        if not user.is_anonymous():
            ChannelSubscription.objects.create(user=user, reply_channel=message.reply_channel)
        message.reply_channel.send({"accept": True})

    def receive(self, content, **kwargs):
        """They sent us a websocket message! We just update the ChannelSubscription lastseen time.."""
        user = self.message.user
        if not user.is_anonymous():
            reply_channel = self.message.reply_channel.name
            ChannelSubscription.objects.filter(user=user, reply_channel=reply_channel).update(
                lastseen_at=timezone.now())

    def disconnect(self, message, **kwargs):
        """The user has disconnected so we remove all their ChannelSubscriptions"""
        user = message.user
        if not user.is_anonymous():
            ChannelSubscription.objects.filter(user=user, reply_channel=message.reply_channel).delete()
