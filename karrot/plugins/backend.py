from django.urls import path, include
import importlib.util
import sys
from os import listdir
from os.path import realpath, join, dirname, basename
from pathlib import Path
from typing import Optional, List


def find_apps_dot_py(base: str) -> Optional[str]:
    try:
        # TODO: find a way to exclude finding things inside lib dirs?
        return str(next(Path(base).rglob('apps.py')))
    except StopIteration:
        return None


def load_backend_plugin(plugin_path: str) -> Optional[str]:
    apps_dot_py = find_apps_dot_py(plugin_path)
    if apps_dot_py:
        # assume the dirname of apps.py is the module name
        # e.g. /path/to/plugins/myplugin/somedir/blah/apps.py
        # -> "blah" is the module and app name
        module_dir = dirname(apps_dot_py)
        plugin_name = basename(module_dir)
        module_name = plugin_name

        if module_name in sys.modules:
            print('module', module_name, 'already exists, bailing')
            return
        try:
            spec = importlib.util.spec_from_file_location(module_name, join(module_dir, '__init__.py'))
            if not spec:
                print('cannot load module spec from', module_name, module_dir)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module_name
        except ModuleNotFoundError as ex:
            print('not a backend plugin', plugin_name, ex)


def load_backend_plugins(plugin_dirs: List[str]) -> List[str]:
    plugins = []
    for plugin_dir in plugin_dirs:
        for name in listdir(plugin_dir):
            plugin_path = realpath(join(plugin_dir, name))
            module_name = load_backend_plugin(plugin_path)
            if module_name:
                plugins.append(module_name)
    return plugins


def get_plugin_urlpatterns(plugins: List[str]):
    patterns = []
    for name in plugins:
        try:
            patterns.append(
                path(
                    f'api/{name}/',
                    # TODO: not sure best way to manage app_name + namespace
                    include((f'{name}.urls', name), namespace=name),
                )
            )
        except ModuleNotFoundError:
            pass
    return patterns
