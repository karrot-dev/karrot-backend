from textwrap import dedent

from django.core.management import BaseCommand
from django.utils.crypto import get_random_string

from karrot.migrate.exporter import export_to_file


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--groups", help="group ids, comma seperated", required=True)
        parser.add_argument("filename", nargs="?", default="export.tar.xz.gpg")

    def handle(self, *args, **options):
        output_filename = options["filename"]
        group_ids = [int(group_id) for group_id in options["groups"].split(",")]
        print("Exporting to", output_filename)

        # generate a password for them, so we can ensure it's long/secure enough
        password = get_random_string(60)

        export_to_file(group_ids, output_filename, password)

        print(
            dedent(
                f"""
            Export complete

            Your file has been encrypted with a passphrase.
            You will need this password to import it again.

            The password is:

                {password}

            Transfer the password and export file separately so if someone has the
            file but not the password they will not be able to access the data.
        """.strip("\n")
            )
        )
