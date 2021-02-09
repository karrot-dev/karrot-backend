#!/bin/bash

set -eu

if test -f config/local_settings.py; then
  echo "Please move your config/local_settings.py file before packaging as this is probably not what you want to be doing..."
  exit 1
fi

# get path to site packages dir
# see https://stackoverflow.com/a/46071447
site_packages=$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')

./manage.py collectstatic

shiv --output-file=karrot-backend \
     --site-packages="$site_packages" \
     --python="/usr/bin/env python3" \
     --entry-point=karrot.cli:run \
     --no-deps .
