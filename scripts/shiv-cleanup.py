#!/usr/bin/env python3
import os
import re
import shutil

# see https://shiv.readthedocs.io/en/latest/#preamble

from pathlib import Path

# variable injected from shiv.bootstrap
site_packages: Path

current = site_packages.parent  # noqa: F821
cache_path = current.parent
name, build_id = current.name.split('_')

if __name__ == "__main__":
    for path in cache_path.iterdir():
        # "." prefix and "_lock" suffix are present on lock files which we also want to remove
        test_path = re.sub('_lock$', '', re.sub(r'^\.', '', path.name))
        if test_path.startswith(f"{name}_") and not test_path.endswith(build_id):
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
