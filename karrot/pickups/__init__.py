from django.apps import AppConfig


class PickupsConfig(AppConfig):
    name = "karrot.pickups"

    def ready(self):
        from . import receivers  # noqa: F401
