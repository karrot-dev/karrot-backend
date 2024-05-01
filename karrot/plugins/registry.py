from dataclasses import dataclass
from os import listdir
from os.path import isdir, join, realpath
from typing import Iterator, Optional

from karrot.plugins.backend import BackendPlugin, load_backend_plugin
from karrot.plugins.frontend import FrontendPlugin, load_frontend_plugin


@dataclass(frozen=True)
class Plugin:
    frontend_plugin: Optional[FrontendPlugin]
    backend_plugin: Optional[BackendPlugin]


def scan_for_plugins(plugin_dir: str) -> Iterator[tuple[str, str]]:
    if isdir(plugin_dir):
        for name in listdir(plugin_dir):
            path = realpath(join(plugin_dir, name))
            yield name, path


def load_plugins(plugin_dir: str) -> dict[str, Plugin]:
    loaded_plugins = {}

    for name, path in scan_for_plugins(plugin_dir):
        frontend_plugin = load_frontend_plugin(name, path)
        backend_plugin = load_backend_plugin(name, path)
        if frontend_plugin or backend_plugin:
            loaded_plugins[name] = Plugin(
                frontend_plugin=frontend_plugin,
                backend_plugin=backend_plugin,
            )

    return loaded_plugins


plugins: dict[str, Plugin] = {}


def initialize_plugins(plugin_dir: str):
    global plugins
    plugins.update(load_plugins(plugin_dir))


def get_frontend_plugins() -> list[FrontendPlugin]:
    global plugins
    entries: list[FrontendPlugin] = []
    for plugin in plugins.values():
        if plugin.frontend_plugin:
            entries.append(plugin.frontend_plugin)
    return entries


def get_frontend_plugin(name: str) -> Optional[FrontendPlugin]:
    global plugins
    plugin = plugins.get(name, None)
    if plugin and plugin.frontend_plugin:
        return plugin.frontend_plugin


def get_backend_plugin_module_names() -> list[str]:
    global plugins
    entries: list[str] = []
    for plugin in plugins.values():
        if plugin.backend_plugin:
            entries.append(plugin.backend_plugin.module_name)
    return entries
