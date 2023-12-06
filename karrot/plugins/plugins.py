import json
from dataclasses import dataclass
from os import listdir
from os.path import isdir, join, realpath, dirname
from pathlib import Path
from typing import List, Optional


@dataclass
class Plugin:
    name: str
    dir: str
    manifest: str
    entry: str
    css_entries: List[str]
    asset_dir: str
    assets: List[str]
    cache_assets: bool


def list_plugins(plugin_dirs: List[str]) -> List[Plugin]:
    plugins = []
    for plugin_dir in plugin_dirs:
        for name in listdir(plugin_dir):
            path = realpath(join(plugin_dir, name))
            if isdir(path):
                manifest = find_manifest(path)
                if manifest:
                    entry, css_entries, assets = process_manifest(manifest)
                    asset_dir = dirname(manifest)
                    plugins.append(
                        Plugin(
                            name=name,
                            dir=path,
                            manifest=manifest,
                            entry=entry,
                            css_entries=css_entries,
                            asset_dir=asset_dir,
                            assets=assets,
                            cache_assets=True,
                        )
                    )
    return plugins


def get_plugin(plugin_dirs: List[str], name: str) -> Optional[Plugin]:
    for plugin in list_plugins(plugin_dirs):
        if plugin.name == name:
            return plugin
    return None


def find_manifest(base: str) -> Optional[str]:
    try:
        return str(next(Path(base).glob('**/manifest.json')))
    except StopIteration:
        return None


def process_manifest(manifest_path: str) -> (List[str], List[str], List[str]):
    entry = []
    css_entries = []
    assets = []
    with open(manifest_path, 'r') as f:
        data: dict = json.loads(f.read())
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
    return entry, css_entries, assets
