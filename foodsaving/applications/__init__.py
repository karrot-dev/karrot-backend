from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    name = 'foodsaving.applications'

    def ready(self):
        from . import receivers  # noqa: F401
