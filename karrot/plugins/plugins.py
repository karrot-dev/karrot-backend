import hashlib
import json
from dataclasses import dataclass
from os import listdir
from os.path import isdir, join, realpath, dirname, exists
from pathlib import Path
from typing import List, Optional, Iterator

from config.settings import PLUGIN_DIRS


@dataclass(frozen=True)
class Plugin:
    name: str
    dir: str
    manifest: str
    manifest_sha256: str
    entry: str
    css_entries: List[str]
    asset_dir: str
    assets: List[str]
    cache_assets: bool


def find_manifest(base: str) -> Optional[str]:
    try:
        return str(next(Path(base).glob('**/manifest.json')))
    except StopIteration:
        return None


def process_manifest(manifest_path: str) -> (str, List[str], List[str], List[str]):
    sha256 = None
    entry = []
    css_entries = []
    assets = []
    with open(manifest_path, 'rb') as f:
        contents = f.read()
        sha256 = hashlib.sha256(contents).hexdigest()
        data: dict = json.loads(contents)
        for item in data.values():
            if 'isEntry' in item and item['isEntry']:
                if entry:
                    print('WARNING: multiple entries, used the first one')
                else:
                    entry = item['file']
                    if 'css' in item:
                        for css_file in item['css']:
                            css_entries.append(css_file)
            assets.append(item['file'])
            if 'css' in item:
                for css_file in item['css']:
                    assets.append(css_file)
            if 'assets' in item:
                for asset_file in item['assets']:
                    assets.append(asset_file)
    return sha256, entry, css_entries, assets


def load_plugin(name: str, path: str) -> Optional[Plugin]:
    if not isdir(path):
        return
    manifest = find_manifest(path)
    if not manifest:
        return
    manifest_sha256, entry, css_entries, assets = process_manifest(manifest)
    asset_dir = dirname(manifest)
    return Plugin(
        name=name,
        dir=path,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        entry=entry,
        css_entries=css_entries,
        asset_dir=asset_dir,
        assets=assets,
        cache_assets=True,
    )


def scan_for_plugins() -> Iterator[tuple[str, str]]:
    for plugin_dir in PLUGIN_DIRS:
        for name in listdir(plugin_dir):
            path = realpath(join(plugin_dir, name))
            yield name, path


def load_plugins() -> dict[str, Plugin]:
    loaded_plugins = {}

    for name, path in scan_for_plugins():
        plugin = load_plugin(name, path)
        if plugin:
            loaded_plugins[name] = plugin

    return loaded_plugins


_plugins: dict[str, Plugin] = load_plugins()


def reload_plugin(name, path):
    plugin = load_plugin(name, path)
    if plugin:
        _plugins[name] = plugin
    elif name in _plugins:
        # didn't reload, gone now!
        _plugins.pop(name)
    return plugin


def manifest_changed(plugin: Plugin) -> bool:
    with open(plugin.manifest, 'rb') as f:
        contents = f.read()
        sha256 = hashlib.sha256(contents).hexdigest()
        return sha256 != plugin.manifest_sha256


def list_plugins() -> List[Plugin]:
    removed_plugins = set(_plugins.keys())

    for name, path in scan_for_plugins():
        if name in removed_plugins:
            removed_plugins.remove(name)
        plugin = _plugins.get(name, None)
        if plugin:
            if path != plugin.dir or not exists(plugin.manifest) or manifest_changed(plugin):
                # path has changed, maybe a different plugin dir
                # or manifest gone
                # reload fresh
                reload_plugin(name, path)
        else:
            # new plugin!
            reload_plugin(name, path)

    for name in removed_plugins:
        if name in _plugins:
            _plugins.pop(name)

    return list(_plugins.values())


def get_plugin(name: str) -> Optional[Plugin]:
    plugin = _plugins.get(name, None)
    if not plugin:
        return None
    if not exists(plugin.manifest) or manifest_changed(plugin):
        # we rescan for the small chance that the plugin is now in another
        # plugin dir...
        for scanned_name, path in scan_for_plugins():
            if scanned_name == name:
                return reload_plugin(name, path)
        # oh, didn't find it, it's gone!
        _plugins.pop(name)
    return _plugins.get(name, None)
