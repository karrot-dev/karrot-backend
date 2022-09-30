from django.apps import AppConfig


class AgreementsConfig(AppConfig):
    name = 'karrot.agreements'

    def ready(self):
        from . import receivers  # noqa: F401
