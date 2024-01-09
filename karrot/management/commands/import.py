from django.contrib.auth.models import AnonymousUser
from django.core.management import BaseCommand

from karrot.migrate.importer import import_from_file


class FakeRequest:
    user = AnonymousUser()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("filename", nargs="?", default="output.tar.xz")

    def handle(self, *args, **options):
        input_filename = options["filename"]
        import_from_file(input_filename)
