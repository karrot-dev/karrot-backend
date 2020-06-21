import os
import subprocess
from django.conf import settings
from django.core.management import BaseCommand

#
# A script to manage database dump and restore.
# Uses database credentials from django settings.
#
# Available commands:
#
#   dump the django database in postgres "custom" format to stdout
#
#     ./manage.py dbutil dump db.dump
#
#   rename the database to something else
#
#     ./manage.py dbutil rename-to karrot-old
#
#   rename the database from something else
#
#     ./manage.py dbutil rename-from karrot-old
#
#   restore a database into the database specified in django settings
#
#     ./manage.py dbutil restore db.dump
#
#   disconnect all postgres connections
#
#     ./manage.py dbutil disconnectall
#
# Without any extra args it will print out the queries it would run.
# Pass --execute to actually run it.
#


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "values", metavar="N", type=str, nargs="+", help="params for the commands"
        )
        parser.add_argument("--execute", action="store_true", dest="execute")

    def handle(self, *args, **options):
        self.do_execute = options["execute"]

        argv = options["values"]

        db = settings.DATABASES["default"]
        command = argv.pop(0)

        environ = os.environ.copy()

        environ.update(
            {
                "PGPASSWORD": db["PASSWORD"],
                "PGHOST": db["HOST"],
                "PGPORT": db["PORT"],
                "PGUSER": db["USER"],
            }
        )

        def execute(args):
            if self.do_execute:
                process = subprocess.run(args, env=environ)
                exit(process.returncode)
            else:
                print(" ".join(args))

        if command == "disconnectall":
            sql = """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE
            datname = 'db' AND
            pid <> pg_backend_pid()
            """
            execute(["psql", "-c", sql])
        elif command == "dump":
            # https://www.postgresql.org/docs/9.6/app-pgdump.html
            # Output a custom-format archive suitable for input into pg_restore.
            # Together with the directory output format, this is the most flexible output format
            # in that it allows manual selection and reordering of archived items during restore.
            # This format is also compressed by default.
            output_file = argv.pop(0)
            execute(["pg_dump", "-Fc", "--file", output_file, db["NAME"]])
        elif command == "restore":
            # https://www.postgresql.org/docs/9.6/app-pgrestore.html
            # The database named in the -d switch can be any database existing in the cluster;
            # pg_restore only uses it to issue the CREATE DATABASE command for mydb.
            # With -C, data is always restored into the database name that appears in the dump file.
            dump = argv.pop(0)
            execute(["pg_restore", "-d", db["NAME"], dump])
        elif command == "rename-to":
            from_name = db["NAME"]
            to_name = argv.pop(0)
            environ["PGDATABASE"] = "postgres"
            sql = 'ALTER DATABASE "{}" RENAME TO "{}"'.format(from_name, to_name)
            execute(["psql", "-c", sql])
        elif command == "rename-from":
            from_name = argv.pop(0)
            to_name = db["NAME"]
            environ["PGDATABASE"] = "postgres"
            sql = 'ALTER DATABASE "{}" RENAME TO "{}"'.format(from_name, to_name)
            execute(["psql", "-c", sql])
