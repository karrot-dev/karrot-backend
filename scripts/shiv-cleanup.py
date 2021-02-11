#!/usr/bin/env python3
import os
import re
import shutil
import psutil

# see https://shiv.readthedocs.io/en/latest/#preamble

from pathlib import Path

# variable injected from shiv.bootstrap
site_packages: Path

current = site_packages.parent  # noqa: F821
cache_path = current.parent
name, build_id = current.name.split('_')


def get_mapped_files():
    files = set()

    for pid in [p.pid for p in psutil.process_iter()]:
        try:
            # quite linux specific... lots of assumptions...
            mapped_file = os.listdir(f"/proc/{pid}/map_files")
            for mapped_file_name in mapped_file:
                files.add(os.readlink(f"/proc/{pid}/map_files/{mapped_file_name}"))
        except PermissionError:
            pass

    return files


if __name__ == "__main__":
    mapped_files = get_mapped_files()
    for path in cache_path.iterdir():
        absolute_path = str(path.resolve())
        # if we have any files in use in this dir, skip...
        if any(mapped_file.startswith(absolute_path) for mapped_file in mapped_files):
            continue
        # "." prefix and "_lock" suffix are present on lock files which we also want to remove
        test_path = re.sub('_lock$', '', re.sub(r'^\.', '', path.name))
        if test_path.startswith(f"{name}_") and not test_path.endswith(build_id):
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
