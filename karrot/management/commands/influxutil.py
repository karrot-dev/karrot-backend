from django.core.management import BaseCommand
from shlex import quote

import os
import subprocess

from django.conf import settings

#
# A script to manage database dump and restore.
# Uses database credentials from django settings.
#
# Available commands:
#
#   export the influxdb database to a file
#   (needs access to the database files, so probably needs sudo)
#
#     ./influx.py export influx.dump
#
#   rewrite the exported file into the new format (store -> place)
#   and a new database name (as the dump contains the db name)
#   writes it to the name of the input file with a .rewritten suffix (e.g. influx.dump.rewritten)
#
#     ./influx.py rewrite influx.dump new-database-name
#
#   import a dump
#
#     ./influx.py import influx.dump.rewritten
#
# Without any extra args it will print out the queries it would run.
# Pass --execute to actually run it.
#


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('values', metavar='arg', type=str, nargs='+', help='params for the commands')
        parser.add_argument('--execute', action='store_true', dest='execute')

    def handle(self, *args, **options):
        self.do_execute = options['execute']

        argv = options['values']

        command = argv.pop(0)

        environ = os.environ.copy()

        environ.update({
            'INFLUX_USERNAME': settings.INFLUXDB_USER,
            'INFLUX_PASSWORD': settings.INFLUXDB_PASSWORD,
        })

        influx_args = ['-host', settings.INFLUXDB_HOST, '-port', settings.INFLUXDB_PORT]

        def execute(args, **kwargs):
            if self.do_execute:
                process = subprocess.run(args, env=environ, **kwargs)
                exit(process.returncode)
            else:
                if isinstance(args, str):
                    print(args)
                else:
                    print(' '.join(args))

        if command == 'export':
            output_file = argv.pop(0)
            execute([
                'sudo',
                'influx_inspect',
                'export',
                '-database',
                settings.INFLUXDB_DATABASE,
                '-datadir',
                '/var/lib/influxdb/data',
                '-waldir',
                '/var/lib/influxdb/wal',
                '-out',
                output_file,
                '-compress',
            ])
        elif command == 'import':
            dump = argv.pop(0)
            execute([
                'influx',
                *influx_args,
                '-import',
                '-compressed',
                '-path={}'.format(dump),
            ])
        elif command == 'rewrite':
            filename = argv.pop(0)
            to_db_name = argv.pop(0)
            sed = '; '.join([
                's/store/place/g',
                's/CREATE DATABASE.*WITH/CREATE DATABASE "{}" WITH/'.format(to_db_name),
                's/CONTEXT-DATABASE:.*/CONTEXT-DATABASE:{}/'.format(to_db_name),
            ])
            execute(
                'zcat {} | sed {} | gzip > {}'.format(quote(filename), quote(sed), quote(filename + '.rewritten')),
                shell=True
            )
