import re
from os.path import basename, isdir, join, splitext
from shutil import rmtree
from zipfile import ZipFile

from config.settings import PLUGIN_DIR


def install_plugin(path_to_zip: str):
    filename = basename(path_to_zip)
    name, _ = splitext(filename)
    plugin_name = re.sub(r"[^0-9a-zA-Z-_]", "", name)
    plugin_dir = join(PLUGIN_DIR, plugin_name)
    if isdir(plugin_dir):
        rmtree(plugin_dir)
    with ZipFile(path_to_zip, "r") as zipfile:
        zipfile.extractall(plugin_dir)
    return plugin_name


def uninstall_plugin(plugin_name: str):
    plugin_dir = join(PLUGIN_DIR, plugin_name)
    if isdir(plugin_dir):
        rmtree(plugin_dir)
