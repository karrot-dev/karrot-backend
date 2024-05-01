import hashlib
import json
from dataclasses import dataclass
from os.path import basename, dirname, isdir
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class FrontendPlugin:
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
        return str(next(entry for entry in Path(base).rglob("manifest.json") if "node_modules" not in str(entry)))
    except StopIteration:
        return None


def process_manifest(manifest_path: str) -> (str, List[str], List[str], List[str]):
    sha256 = None
    entry = []
    css_entries = []
    assets = []
    with open(manifest_path, "rb") as f:
        contents = f.read()
        sha256 = hashlib.sha256(contents).hexdigest()
        data: dict = json.loads(contents)
        for item in data.values():
            if "isEntry" in item and item["isEntry"]:
                if entry:
                    print("WARNING: multiple entries, used the first one")
                else:
                    entry = item["file"]
                    if "css" in item:
                        for css_file in item["css"]:
                            css_entries.append(css_file)
            assets.append(item["file"])
            if "css" in item:
                for css_file in item["css"]:
                    assets.append(css_file)
            if "assets" in item:
                for asset_file in item["assets"]:
                    assets.append(asset_file)
    return sha256, entry, css_entries, assets


def load_frontend_plugin(name: str, plugin_dir: str) -> Optional[FrontendPlugin]:
    if not isdir(plugin_dir):
        return
    manifest = find_manifest(plugin_dir)
    if not manifest:
        return
    manifest_sha256, entry, css_entries, assets = process_manifest(manifest)
    asset_dir = dirname(manifest)
    # the manifest can be in the root dir, or in a .vite subdir
    if basename(asset_dir) == ".vite":
        asset_dir = dirname(asset_dir)
    return FrontendPlugin(
        name=name,
        dir=plugin_dir,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        entry=entry,
        css_entries=css_entries,
        asset_dir=asset_dir,
        assets=assets,
        cache_assets=True,
    )
