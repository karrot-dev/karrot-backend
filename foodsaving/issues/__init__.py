from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = 'foodsaving.issues'

    def ready(self):
        from . import receivers  # noqa: F401
