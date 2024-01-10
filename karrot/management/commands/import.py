from django.contrib.auth.models import AnonymousUser
from django.core.management import BaseCommand, call_command

from karrot.migrate.importer import import_from_file


class FakeRequest:
    user = AnonymousUser()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("filename", nargs="?", default="export.tar.xz")

    def handle(self, *args, **options):
        input_filename = options["filename"]
        print("Importing", input_filename)
        import_from_file(input_filename)
        call_command("flush_sized_images_cache")
        call_command("warm_images")
        print("Import complete")
