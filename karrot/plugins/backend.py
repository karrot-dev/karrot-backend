import importlib.util
import sys
from dataclasses import dataclass
from os.path import basename, dirname, join
from pathlib import Path
from typing import List, Optional

from django.urls import include, path


@dataclass(frozen=True)
class BackendPlugin:
    name: str
    dir: str
    module_name: str


def find_apps_dot_py(base: str) -> Optional[str]:
    try:
        return str(next(entry for entry in Path(base).rglob("apps.py") if "site-packages" not in str(entry)))
    except StopIteration:
        return None


def load_backend_plugin(name: str, plugin_dir: str) -> Optional[BackendPlugin]:
    apps_dot_py = find_apps_dot_py(plugin_dir)
    if apps_dot_py:
        # assume the dirname of apps.py is the module name
        # e.g. /path/to/plugins/myplugin/somedir/blah/apps.py
        # -> "blah" is the module and app name
        module_dir = dirname(apps_dot_py)
        plugin_name = basename(module_dir)
        module_name = plugin_name

        if module_name in sys.modules:
            raise RuntimeError(f"there is module named {module_name} already loaded")
        try:
            spec = importlib.util.spec_from_file_location(module_name, join(module_dir, "__init__.py"))
            if not spec:
                print("cannot load module spec from", module_name, module_dir)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return BackendPlugin(
                name=name,
                dir=plugin_dir,
                module_name=module_name,
            )
        except ModuleNotFoundError as ex:
            raise RuntimeError(f"could not load backend plugin {plugin_name}") from ex


def get_plugin_urlpatterns(plugins: List[str]):
    patterns = []
    for name in plugins:
        try:
            patterns.append(
                path(
                    f"api/plugins/{name}/",
                    include((f"{name}.urls", name), namespace=name),
                )
            )
        except ModuleNotFoundError as e:
            print("no plugin urls", e)
    return patterns
