from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    name = 'karrot.applications'

    def ready(self):
        from . import receivers  # noqa: F401
