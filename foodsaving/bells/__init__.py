from django.apps import AppConfig


class BellsConfig(AppConfig):
    name = 'foodsaving.bells'

    def ready(self):
        from . import receivers  # noqa: F401
        from . import tasks  # noqa: F401
