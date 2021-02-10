import httpx
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.security import websocket
from django.conf import settings
from django.core.asgi import get_asgi_application
from starlette.responses import Response

from starlette.staticfiles import StaticFiles

from karrot.subscriptions.consumers import WebsocketConsumer, TokenAuthMiddleware


class OriginValidatorThatAllowsFileUrls(websocket.OriginValidator):
    # We need to allow file urls in the origin header for our cordova app
    def valid_origin(self, parsed_origin):
        if parsed_origin is not None and parsed_origin.scheme == 'file':
            return True
        return super().valid_origin(parsed_origin)


def AllowedHostsAndFileOriginValidator(application):
    # copied from channels.security.websocket
    allowed_hosts = settings.ALLOWED_HOSTS
    if settings.DEBUG and not allowed_hosts:
        allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
    return OriginValidatorThatAllowsFileUrls(application, allowed_hosts)


api_app = get_asgi_application()
api_prefixes = ['/api/', '/docs/', '/api-auth/']
media_app = StaticFiles(directory=settings.MEDIA_ROOT)

if settings.DEBUG:
    static_app = None
    api_prefixes += ['/static/']
else:
    static_app = StaticFiles(directory=settings.STATIC_ROOT)

if settings.FRONTEND_DIR:
    frontend_app = StaticFiles(directory=settings.FRONTEND_DIR, html=True)
else:
    frontend_app = None


async def http_app(scope, receive, send):
    app = None
    if 'path' in scope:
        path = scope['path']
        if any(path.startswith(prefix) for prefix in api_prefixes):
            app = api_app
        elif path.startswith('/media'):
            scope['path'] = path[len('/media'):]
            app = media_app
        elif static_app and path.startswith('/static/'):
            scope['path'] = path[len('/static'):]
            app = static_app
        elif path.startswith('/community_proxy/'):
            async with httpx.AsyncClient() as client:
                proxy_url = 'https://community.foodsaving.world' + path[len('/community_proxy'):]
                r = await client.get(proxy_url)
                keep_headers = ['cache-control', 'last-modified']
                headers = {}
                for key in keep_headers:
                    if key in r.headers:
                        headers[key] = r.headers[key]
                print('headers are', r.headers)
                response = Response(
                    r.content,
                    status_code=r.status_code,
                    headers=headers,
                    media_type=r.headers['content-type'],
                )
                await response(scope, receive, send)
        else:
            app = frontend_app

    if not app:
        raise Exception('invalid')

    return await app(scope, receive, send)


application = ProtocolTypeRouter({
    'http':
    http_app,
    'websocket':
    AllowedHostsAndFileOriginValidator(
        AuthMiddlewareStack(
            TokenAuthMiddleware(
                WebsocketConsumer.as_asgi(),
            ),
        ),
    ),
})
