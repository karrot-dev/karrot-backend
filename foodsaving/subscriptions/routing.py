from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.security.websocket import AllowedHostsOriginValidator

from .consumers import WebsocketConsumer, TokenAuthMiddleware

application = ProtocolTypeRouter({
    'websocket': AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            AuthMiddlewareStack(
                WebsocketConsumer,
            ),
        ),
    ),
})
