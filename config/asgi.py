"""
ASGI entrypoint. Runs the application defined in the ASGI_APPLICATION setting.
"""

import os

from channels.routing import get_default_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_default_application()
