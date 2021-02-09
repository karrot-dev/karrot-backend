"""
ASGI entrypoint. Configures Django and then runs the application
defined in the ASGI_APPLICATION setting.
"""

import os
import django
import uvicorn

from channels.routing import get_default_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
application = get_default_application()


def run():
    uvicorn.run(
        "config.asgi:application",
        host="127.0.0.1",
        port=5000,
        log_level="info",
        workers=0,
    )


if __name__ == '__main__':
    run()
