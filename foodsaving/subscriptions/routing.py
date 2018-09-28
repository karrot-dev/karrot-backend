from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.security import websocket
from django.conf import settings

from .consumers import WebsocketConsumer, TokenAuthMiddleware


class OriginValidatorThatAllowsFileUrls(websocket.OriginValidator):
    # We need to allow file urls in the origin header for our cordova app
    def valid_origin(self, parsed_origin):
        print(parsed_origin)
        if parsed_origin is not None and parsed_origin.scheme == 'file':
            return True
        return super().valid_origin(parsed_origin)


def AllowedHostsAndFileOriginValidator(application):
    # copied from channels.security.websocket
    allowed_hosts = settings.ALLOWED_HOSTS
    if settings.DEBUG and not allowed_hosts:
        allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
    return OriginValidatorThatAllowsFileUrls(application, allowed_hosts)


application = ProtocolTypeRouter({
    'websocket':
    AllowedHostsAndFileOriginValidator(
        TokenAuthMiddleware(
            AuthMiddlewareStack(
                WebsocketConsumer,
            ),
        ),
    ),
})
