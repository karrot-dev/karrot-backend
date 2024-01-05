from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    name = "karrot.webhooks"

    def ready(self):
        from . import receivers  # noqa: F401
