from django.apps import AppConfig


class IssuesConfig(AppConfig):
    name = "karrot.issues"

    def ready(self):
        from . import receivers  # noqa: F401
