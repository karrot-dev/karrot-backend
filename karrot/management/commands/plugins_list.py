from django.core.management.base import BaseCommand

from karrot.plugins.frontend import list_plugins


class Command(BaseCommand):
    def handle(self, *args, **options):
        for plugin in list_plugins():
            print(plugin.name)
            print("  dir:", plugin.dir)
            print("  asset_dir:", plugin.asset_dir)
            print("  entry:", plugin.entry)
            if plugin.css_entries:
                print("  css_entries:")
                for css_entry in plugin.css_entries:
                    print("  -", css_entry)
            if plugin.assets:
                print("  assets:")
                for asset in plugin.assets:
                    print("  -", asset)
