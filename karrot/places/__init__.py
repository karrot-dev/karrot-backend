from django.apps import AppConfig


class PlacesConfig(AppConfig):
    name = "karrot.places"

    def ready(self):
        from . import receivers  # noqa: F401
