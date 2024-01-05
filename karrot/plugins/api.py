from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from config.settings import PLUGIN_ASSETS_PUBLIC_PREFIX
from karrot.plugins.frontend import Plugin, list_plugins


def serialize_plugin(plugin: Plugin):
    def get_public_path(path):
        return "/".join([PLUGIN_ASSETS_PUBLIC_PREFIX.rstrip("/"), plugin.name, path])

    return {
        "name": plugin.name,
        "entry": get_public_path(plugin.entry),
        "css_entries": [get_public_path(css) for css in plugin.css_entries],
    }


class PluginViewSet(ViewSet):
    def list(self, request):
        plugins = list_plugins()
        return Response([serialize_plugin(plugin) for plugin in plugins])
