import os

from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_defaults():
    return dotenv_values(os.path.join(BASE_DIR, 'config', 'options.env'))


def get_options():
    options = {}
    defaults = get_defaults()

    for key, default in defaults.items():
        value = os.environ.get(key, default)
        options[key] = value if value else None

    is_dev = options['MODE'] == 'dev'

    # some more complex defaults that depend on other values

    if not options['WORKER_IMMEDIATE']:
        # three possiblities:
        # - set explicitly
        # - if MODE=dev, default to true
        # - otherwise default to false
        options['WORKER_IMMEDIATE'] = 'true' if is_dev else 'false'

    if not options['LISTEN_CONCURRENCY']:
        # WEB_CONCURRENCY is something uvicorn recognises, maybe others too?
        options['LISTEN_CONCURRENCY'] = os.environ.get('WEB_CONCURRENCY', '1')

    if not options['GEOIP_PATH']:
        options['GEOIP_PATH'] = 'maxmind-data' if is_dev else '/var/lib/GeoIP'

    return options
