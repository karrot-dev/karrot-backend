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

    def check_pid(pid):
        try:
            # quite linux specific... lots of assumptions...
            mapped_file = os.listdir(f"/proc/{pid}/map_files")
            for mapped_file_name in mapped_file:
                files.append(os.readlink(f"/proc/{pid}/map_files/{mapped_file_name}"))
        except PermissionError:
            pass

    for p in psutil.process_iter():
        check_pid(p.pid)

    return files


if __name__ == "__main__":
    mapped_files = get_mapped_files()
    for path in cache_path.iterdir():
        if path in mapped_files:
            print('skipping cleanup for', path)
            continue
        # "." prefix and "_lock" suffix are present on lock files which we also want to remove
        test_path = re.sub('_lock$', '', re.sub(r'^\.', '', path.name))
        if test_path.startswith(f"{name}_") and not test_path.endswith(build_id):
            print('shiv cleanup', path)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
