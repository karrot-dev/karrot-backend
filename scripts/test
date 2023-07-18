#!/bin/bash

# Simple test wrapper that uses the test_settings.py

set -eu

export DJANGO_SETTINGS_MODULE=config.test_settings

python manage.py test "$@"
