#!/bin/bash

set -eu

# get path to site packages dir
# see https://stackoverflow.com/a/46071447
site_packages=$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')

shiv --output-file=karrot.pyz \
     --site-packages="$site_packages" \
     --python="/usr/bin/env python3" \
     --console-script=daphne \
     --no-deps .
     #--entry-point=karrot.__main__.main \
