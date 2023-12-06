from rest_framework.viewsets import ViewSet
from rest_framework.response import Response

from config.settings import PLUGIN_DIRS, PLUGIN_ASSETS_PUBLIC_PREFIX
from karrot.plugins.plugins import list_plugins, Plugin


def serialize_plugin(plugin: Plugin):
    def get_public_path(path):
        return '/'.join([PLUGIN_ASSETS_PUBLIC_PREFIX.rstrip('/'), plugin.name, path])

    return {
        "name": plugin.name,
        "entry": get_public_path(plugin.entry),
        "css_entries": [get_public_path(css) for css in plugin.css_entries],
    }


class PluginViewSet(ViewSet):
    def list(self, request):
        plugins = list_plugins(PLUGIN_DIRS)
        return Response([serialize_plugin(plugin) for plugin in plugins])
