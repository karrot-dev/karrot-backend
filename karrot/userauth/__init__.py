from django.apps import AppConfig


class UserAuthConfig(AppConfig):
    name = 'karrot.userauth'

    def ready(self):
        from . import receivers  # noqa: F401
