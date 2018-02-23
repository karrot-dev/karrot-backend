from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    name = 'foodsaving.webhooks'

    def ready(self):
        pass
        # from . import receivers  # noqa: F401
