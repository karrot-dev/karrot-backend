import email
import re
import time

import httpx
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.security import websocket
from django.conf import settings
from django.core.asgi import get_asgi_application
from starlette.datastructures import MutableHeaders
from starlette.responses import Response

from starlette.staticfiles import StaticFiles

from karrot.subscriptions.consumers import WebsocketConsumer, TokenAuthMiddleware

ONE_YEAR = 60 * 60 * 24 * 365


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


def http_date(epoch_time):
    return email.utils.formatdate(epoch_time, usegmt=True)


class CommunityProxy:
    def __init__(self, proxy_url):
        self.proxy_url = re.sub(r'/$', '', proxy_url)  # no trailing slash

    async def __call__(self, scope, receive, send):
        async with httpx.AsyncClient() as client:
            path = scope['path']
            proxy_url = self.proxy_url + path[len('/community_proxy'):]
            r = await client.get(proxy_url)
            keep_headers = ['cache-control', 'last-modified']
            headers = {}
            for key in keep_headers:
                if key in r.headers:
                    headers[key] = r.headers[key]
            response = Response(
                r.content,
                status_code=r.status_code,
                headers=headers,
                media_type=r.headers['content-type'],
            )
            return await response(scope, receive, send)


class ExpiresMax:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        # Borrowing from:
        # https://github.com/florimondmanca/asgi-caches/blob/master/src/asgi_caches/utils/cache.py
        # From section 14.12 of RFC2616:
        # "HTTP/1.1 servers SHOULD NOT send Expires dates more than
        # one year in the future."
        max_age = ONE_YEAR

        async def send_cached(message):
            # borrowing from https://github.com/encode/starlette/blob/master/starlette/middleware/cors.py
            if message["type"] != "http.response.start":
                return await send(message)
            message.setdefault("headers", [])
            headers = MutableHeaders(scope=message)
            headers.update({
                'Cache-Control': f'max-age={max_age}',
                'Expires': http_date(time.time() + max_age),
            })
            await send(message)

        return await self.app(scope, receive, send_cached)


def cached(app):
    return ExpiresMax(app) if app else None


api_app = get_asgi_application()
api_prefixes = ['/api/', '/docs/', '/api-auth/']
media_app = StaticFiles(directory=settings.MEDIA_ROOT)

if settings.DEBUG:
    # in DEBUG mode they are served by the main api app via config/urls.py
    static_app = None
    api_prefixes += ['/static/']
else:
    static_app = StaticFiles(directory=settings.STATIC_ROOT)

if settings.FRONTEND_DIR:
    frontend_app = StaticFiles(directory=settings.FRONTEND_DIR, html=True)
else:
    frontend_app = None

if settings.PROXY_DISCOURSE_URL:
    community_proxy = CommunityProxy(settings.PROXY_DISCOURSE_URL)
else:
    community_proxy = None

enable_static_cache = not settings.DEBUG

if enable_static_cache:
    media_app = cached(media_app)
    frontend_app = cached(frontend_app)


async def http_router(scope, receive, send):
    app = None
    if 'path' in scope:
        path = scope['path']
        if any(path.startswith(prefix) for prefix in api_prefixes):
            app = api_app
        elif path.startswith('/media/'):
            scope['path'] = path[len('/media'):]
            app = media_app
        elif static_app and path.startswith('/static/'):
            scope['path'] = path[len('/static'):]
            app = static_app
        elif settings.PROXY_DISCOURSE_URL and path.startswith('/community_proxy/'):
            app = community_proxy
        else:
            app = frontend_app

    if not app:
        raise Exception('invalid request')

    return await app(scope, receive, send)


application = ProtocolTypeRouter({
    'http':
    http_router,
    'websocket':
    AllowedHostsAndFileOriginValidator(
        AuthMiddlewareStack(
            TokenAuthMiddleware(
                WebsocketConsumer.as_asgi(),
            ),
        ),
    ),
})
