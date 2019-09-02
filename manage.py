#!/usr/bin/env python
import os
import sys

# Apply monkey-patch if we are running the huey consumer.
if 'run_huey' in sys.argv:
    from gevent import monkey
    monkey.patch_all()

# Always execute scheduled tasks when testing
if 'test' in sys.argv:
    from huey.api import Huey

    def ready_to_run(*args, **kwargs):
        return True

    Huey._ready_to_run = Huey.ready_to_run
    Huey.ready_to_run = ready_to_run

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
