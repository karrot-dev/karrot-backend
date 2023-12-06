from django.core.management.base import BaseCommand

from karrot.plugins.plugins import list_plugins
from config.settings import PLUGIN_DIRS


class Command(BaseCommand):
    def handle(self, *args, **options):
        for plugin in list_plugins(PLUGIN_DIRS):
            print(plugin.name)
            print('  dir:', plugin.dir)
            print('  asset_dir:', plugin.asset_dir)
            print('  entry:', plugin.entry)
            if plugin.css_entries:
                print('  css_entries:')
                for css_entry in plugin.css_entries:
                    print('  -', css_entry)
            if plugin.assets:
                print('  assets:')
                for asset in plugin.assets:
                    print('  -', asset)
