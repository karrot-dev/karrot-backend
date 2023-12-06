from django.apps import AppConfig


class PluginsConfig(AppConfig):
    name = 'karrot.plugins'

    def ready(self):
        pass
