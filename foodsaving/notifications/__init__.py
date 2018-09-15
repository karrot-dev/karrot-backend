from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'foodsaving.notifications'

    def ready(self):
        from . import receivers  # noqa: F401
        from . import tasks  # noqa: F401
