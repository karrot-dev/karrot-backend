from django.core.management import BaseCommand

from karrot.migrate.exporter import export_to_file


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--groups", help="group ids", required=True)
        parser.add_argument("filename", nargs="?", default="output.tar.xz")

    def handle(self, *args, **options):
        output_filename = options["filename"]
        group_ids = [int(group_id) for group_id in options["groups"].split(",")]
        export_to_file(group_ids, output_filename)
