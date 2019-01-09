from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = 'foodsaving.cases'

    def ready(self):
        from . import receivers  # noqa: F401
