from django.apps import AppConfig


class ActivitiesConfig(AppConfig):
    name = 'karrot.activities'

    def ready(self):
        from . import receivers  # noqa: F401
