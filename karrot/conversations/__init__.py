from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    name = "karrot.conversations"

    def ready(self):
        from . import receivers  # noqa: F401
