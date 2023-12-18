from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "karrot.notifications"

    def ready(self):
        from . import receivers  # noqa: F401
        from . import tasks  # noqa: F401
