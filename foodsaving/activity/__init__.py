from django.apps import AppConfig


class ActivityConfig(AppConfig):
    name = 'foodsaving.activity'

    def ready(self):
        from . import receivers  # noqa: F401
