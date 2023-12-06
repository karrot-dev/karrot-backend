from os.path import normpath, join
from typing import List
from asgiref.sync import sync_to_async

import aiofiles.os
from starlette.responses import FileResponse
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from karrot.plugins.plugins import get_plugin
from karrot.utils.asgi_utils import expires_max_headers

not_found = Response('not found', status_code=404, media_type='text/plain')

get_plugin_async = sync_to_async(get_plugin)


class PluginAssets:
    def __init__(self, plugin_dirs: List[str]):
        super().__init__()
        self.plugin_dirs = plugin_dirs

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

        plugin = await get_plugin_async(self.plugin_dirs, plugin_name)
        if not plugin:
            return not_found

        if path not in plugin.assets:
            # we only serve up the specific assets listed
            return not_found

        full_path = join(plugin.asset_dir, path)

        stat_result = await aiofiles.os.stat(full_path)

        headers = None
        if plugin.cache_assets:
            headers = expires_max_headers

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
        path = path.lstrip("/")
        parts = path.split("/")
        if len(parts) < 2:
            return
        plugin_name = parts[0]
        return plugin_name, normpath(join(*parts[1:]))
