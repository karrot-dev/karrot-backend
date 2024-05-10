import time
from os.path import join, normpath

import aiofiles.os
from asgiref.sync import sync_to_async
from django.conf import settings
from starlette.responses import FileResponse, Response
from starlette.types import Receive, Scope, Send

from karrot.plugins.registry import get_frontend_plugin
from karrot.utils.asgi_utils import http_date, max_age

not_found = Response("not found", status_code=404, media_type="text/plain")

# TODO: I don't think we need this async version any more now it's simpler
get_frontend_plugin_async = sync_to_async(get_frontend_plugin)


class PluginAssets:
    """An ASGI app that serves up asset files for plugins

    It's anticipated the frontend plugins won't have *so* many asset files and it'll
    be fine to serve them using the python webserver.

    We do the best we can to make them serve up fast :)
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point.
        """
        assert scope["type"] == "http"
        response = await self.get_response(scope)
        return await response(scope, receive, send)

    async def get_response(self, scope):
        plugin_name, path = self.split_plugin_name_and_asset_path(scope["path"])
        if not plugin_name or not path:
            return not_found

        plugin = await get_frontend_plugin_async(plugin_name)
        if not plugin:
            return not_found

        if path not in plugin.assets:
            # we only serve up the specific assets listed
            return not_found

        full_path = join(plugin.asset_dir, path)

        stat_result = await aiofiles.os.stat(full_path)

        headers = None
        if plugin.cache_assets:
            headers = {
                "Cache-Control": f"max-age={max_age}",
                "Expires": http_date(time.time() + max_age),
            }

        return FileResponse(
            full_path,
            headers=headers,
            stat_result=stat_result,
        )

    @staticmethod
    def split_plugin_name_and_asset_path(path: str) -> (str, str):
        """
        Given the ASGI scope, return the `path` string to serve up,
        with OS specific path separators, and any '..', '.' components removed.
        """
        if not path.startswith(settings.PLUGIN_ASSETS_PUBLIC_PREFIX):
            return "", ""
        path = path[len(settings.PLUGIN_ASSETS_PUBLIC_PREFIX.rstrip("/")) :]
        parts = path.lstrip("/").split("/")
        if len(parts) < 2:
            return "", ""
        plugin_name = parts[0]
        return plugin_name, normpath(join(*parts[1:]))
