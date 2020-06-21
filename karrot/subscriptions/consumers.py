from base64 import b64decode

from channels.auth import UserLazyObject
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer
from channels.middleware import BaseMiddleware
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication

from karrot.subscriptions.models import ChannelSubscription

token_auth = TokenAuthentication()


def get_auth_token_from_subprotocols(subprotocols):
    prefix = "karrot.token.value."
    for protocol in subprotocols:
        if protocol.startswith(prefix):
            value = protocol[len(prefix) :]
            if len(value) % 4:
                # not a multiple of 4, add padding:
                value += "=" * (4 - len(value) % 4)
            return b64decode(value).decode("ascii")
    return None


class TokenAuthMiddleware(BaseMiddleware):
    """
    Middleware which populates scope["user"] from a auth token provided as websocket protocol header
    Used by the cordova app

    scope['user'] is usually provided by AuthMiddleware, we just override it if we find a token.
    """

    def populate_scope(self, scope):
        if "user" not in scope:
            scope["user"] = UserLazyObject()

    async def resolve_scope(self, scope):
        token = get_auth_token_from_subprotocols(scope.get("subprotocols", []))
        if token:
            user, _ = await database_sync_to_async(token_auth.authenticate_credentials)(
                token
            )
            if user:
                scope["user"]._wrapped = user


class WebsocketConsumer(JsonWebsocketConsumer):
    def connect(self):
        """The user has connected! Register their channel subscription."""
        subprotocol = None
        if "user" in self.scope:
            user = self.scope["user"]
            if not user.is_anonymous:
                ChannelSubscription.objects.create(
                    user=user, reply_channel=self.channel_name
                )

                if "karrot.token" in self.scope["subprotocols"]:
                    subprotocol = "karrot.token"

        self.accept(subprotocol)

    def message_send(self, content, **kwargs):
        if "text" not in content:
            raise Exception("you must set text on the content")
        self.send(content["text"])

    def receive_json(self, content, **kwargs):
        """They sent us a websocket message!"""
        if "user" in self.scope:
            user = self.scope["user"]
            if not user.is_anonymous:
                subscriptions = ChannelSubscription.objects.filter(
                    user=user, reply_channel=self.channel_name
                )
                update_attrs = {"lastseen_at": timezone.now()}
                message_type = content.get("type", None)
                if message_type == "away":
                    update_attrs["away_at"] = timezone.now()
                elif message_type == "back":
                    update_attrs["away_at"] = None
                elif message_type == "ping":
                    self.send_json({"type": "pong"})
                subscriptions.update(**update_attrs)

    def disconnect(self, close_code):
        """The user has disconnected so we remove all their ChannelSubscriptions"""
        if "user" in self.scope:
            user = self.scope["user"]
            if not user.is_anonymous:
                ChannelSubscription.objects.filter(
                    user=user, reply_channel=self.channel_name
                ).delete()
