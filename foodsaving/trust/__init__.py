from django.apps import AppConfig


class TrustConfig(AppConfig):
    name = 'foodsaving.trust'

    def ready(self):
        from . import receivers  # noqa: F401
