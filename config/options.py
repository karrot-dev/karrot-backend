import os
import subprocess
from typing import Literal

from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_defaults(filename: Literal['options.env', 'dev.env']):
    return dotenv_values(os.path.join(BASE_DIR, 'config', filename))


def get_git_rev():
    with open(os.path.devnull, "w+") as null:
        try:
            release = (
                subprocess.Popen(
                    ["git", "rev-parse", "HEAD"],
                    stdout=subprocess.PIPE,
                    stderr=null,
                    stdin=null,
                ).communicate()[0].strip().decode("utf-8")
            )
        except (OSError, IOError):
            pass

    if release:
        return release

    revision_file = os.path.join(BASE_DIR, 'karrot', 'COMMIT')
    if os.path.exists(revision_file):
        with open(revision_file, 'r') as f:
            return f.read().strip()


def get_options():
    options = {}
    defaults = get_defaults('options.env')

    # we assume this has been set early...
    is_dev = os.environ.get('MODE') == 'dev'

    if is_dev:
        defaults.update(get_defaults('dev.env'))

    for key, default in defaults.items():
        value = os.environ.get(key, default)
        options[key] = value if value else None

    # some more complex defaults that depend on other values

    if not options['LISTEN_CONCURRENCY']:
        # WEB_CONCURRENCY is something uvicorn recognises, maybe others too?
        options['LISTEN_CONCURRENCY'] = os.environ.get('WEB_CONCURRENCY', '1')

    if not options['GEOIP_PATH']:
        options['GEOIP_PATH'] = 'maxmind-data' if is_dev else '/var/lib/GeoIP'

    if options['SENTRY_RELEASE_USE_GIT_REV'] and not options['SENTRY_RELEASE']:
        rev = get_git_rev()
        if rev:
            options['SENTRY_RELEASE'] = rev

    return options
