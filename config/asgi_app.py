from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.db.backends.signals import connection_created
from django.dispatch import receiver
from starlette.responses import Response

from starlette.staticfiles import StaticFiles

from karrot.plugins.asgi import PluginAssets
from karrot.utils.asgi_utils import CommunityProxy, AllowedHostsAndFileOriginValidator, cached
from karrot.subscriptions.consumers import WebsocketConsumer, TokenAuthMiddleware


@receiver(connection_created)
def setup_postgres(connection, **kwargs):
    """Set the statement timeout here, as it's only for web requests"""
    if connection.vendor != 'postgresql':
        return

    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout TO {};".format(settings.REQUEST_DATABASE_TIMEOUT_MILLISECONDS))


api_app = get_asgi_application()
api_prefixes = ['/api/', '/docs/', '/api-auth/', '/silk/']

plugin_assets_app = PluginAssets(settings.PLUGIN_DIRS)
plugin_assets_prefix = settings.PLUGIN_ASSETS_PUBLIC_PREFIX

if settings.DEBUG:
    api_prefixes.append('/_templates')

media_app = StaticFiles(directory=settings.MEDIA_ROOT)

frontend_app = None
static_app = None
community_proxy_app = None

if settings.DEBUG:
    # in DEBUG mode they are served by the main api app via config/urls.py
    api_prefixes += ['/static/', '/_templates']
else:
    static_app = StaticFiles(directory=settings.STATIC_ROOT)

if settings.FRONTEND_DIR:
    frontend_app = StaticFiles(directory=settings.FRONTEND_DIR, html=True)

if settings.PROXY_DISCOURSE_URL:
    community_proxy_app = CommunityProxy(proxy_url=settings.PROXY_DISCOURSE_URL)

enable_static_cache = not settings.DEBUG

if enable_static_cache:
    media_app = cached(media_app)
    frontend_app = cached(frontend_app)

not_found = Response('not found', status_code=404, media_type='text/plain')


async def http_router(scope, receive, send):
    app = None
    if 'path' in scope:
        path = scope['path']
        if path.startswith(plugin_assets_prefix):
            # putting this one first, so it can be nested inside /api/
            scope['path'] = path[len(plugin_assets_prefix.rstrip('/')):]
            app = plugin_assets_app
        elif any(path.startswith(prefix) for prefix in api_prefixes):
            app = api_app
        elif path.startswith('/media/'):
            scope['path'] = path[len('/media'):]
            app = media_app
        elif static_app and path.startswith('/static/'):
            scope['path'] = path[len('/static'):]
            app = static_app
        elif community_proxy_app and path.startswith('/community_proxy/'):
            app = community_proxy_app
        else:
            app = frontend_app

    if not app:
        app = not_found

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
