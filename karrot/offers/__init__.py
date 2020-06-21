from django.apps import AppConfig


class OffersConfig(AppConfig):
    name = "karrot.offers"

    def ready(self):
        from . import receivers  # noqa: F401
