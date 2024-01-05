from os.path import isdir, realpath


def normalize_plugin_dirs(plugin_dirs: str):
    return [plugin_dir for plugin_dir in [realpath(val.strip()) for val in plugin_dirs.split(",")] if isdir(plugin_dir)]
