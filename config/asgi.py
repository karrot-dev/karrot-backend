"""
ASGI entrypoint. Configures Django and then runs the application
defined in the ASGI_APPLICATION setting.
"""

import os
import django
from channels.routing import get_default_application

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
channels_application = get_default_application()

routes = [
    Mount('/api', app=channels_application, name='api'),
    Mount('/media', app=StaticFiles(directory='uploads'), name="media"),
    Mount('/', app=StaticFiles(directory='/code/karrot/karrot-frontend/dist/pwa/', html=True), name="frontend"),
]

application = Starlette(routes=routes)
