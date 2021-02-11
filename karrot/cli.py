import os

import click
import uvicorn
from click import pass_context
from daphne.cli import CommandLineInterface
from django.core import management
from django.conf import settings
import django
from django.core.management import execute_from_command_line
from dotenv import load_dotenv

from config.options import get_options


def setup(env_files=()):
    for env_file in reversed(env_files):
        # in reversed order so that the last one passed on the command line
        # has the highest priority, which means applied first
        # (actual env vars still have higher priority)
        load_dotenv(env_file)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


@click.group()
@click.option('env_files', '--env', help='path to env file', multiple=True)
def cli(env_files):
    setup(env_files)


@cli.command(help='run a web server')
def server():
    server_uvicorn() if settings.LISTEN_SERVER == 'uvicorn' else server_daphne()


@cli.command(help='run a huey worker')
def worker():
    management.call_command("run_huey")


@cli.command(help='alias for django "check" command')
def check():
    management.call_command("check")


@cli.command(help='alias for django "shell_plus" command')
def shell():
    management.call_command("shell_plus")


@cli.command(help='alias for django "dbshell" command')
def dbshell():
    management.call_command("dbshell")


@cli.command(
    help='run a django manage.py command', context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@pass_context
def manage(ctx):
    print('running manage', ctx.args)
    execute_from_command_line(['', *ctx.args])


@cli.command(help='alias for django "migrate" command')
def migrate():
    management.call_command("migrate", interactive=False)


@cli.command(help='print the working directory')
def basedir():
    print(settings.BASE_DIR)


@cli.command(help='show the effective config')
def config():
    for key, value in get_options().items():
        print(key + '=' + (value if value else ''))


def server_uvicorn():
    # https://www.uvicorn.org/settings/
    # TODO: do I need to have '--ws-protocol karrot.token' somehow?
    options = {
        'log_level': 'info',
        'workers': settings.LISTEN_CONCURRENCY,
    }
    if settings.LISTEN_FD:
        options['fd'] = int(settings.LISTEN_FD)

    if settings.LISTEN_HOST:
        options['host'] = settings.LISTEN_HOST

    if settings.LISTEN_PORT:
        options['port'] = int(settings.LISTEN_PORT)

    if settings.LISTEN_SOCKET:
        options['uds'] = settings.LISTEN_SOCKET

    uvicorn.run("config.asgi:application", **options)


def server_daphne():
    args = []
    args += ['--ws-protocol', 'karrot.token']
    args += ['--proxy-headers']

    if settings.LISTEN_CONCURRENCY > 1:
        raise Exception('LISTEN_CONCURRENCY cannot be above 1 if using daphne')

    if settings.LISTEN_FD:
        args += ['--fd', settings.LISTEN_FD]

    if settings.LISTEN_ENDPOINT:
        args += ['--endpoint', settings.LISTEN_ENDPOINT]

    if settings.LISTEN_HOST:
        args += ['--bind', settings.LISTEN_HOST]

    if settings.LISTEN_PORT:
        args += ['--port', settings.LISTEN_PORT]

    if settings.LISTEN_SOCKET:
        args += ['--unix-socket', settings.LISTEN_SOCKET]

    args += ['config.asgi:application']

    CommandLineInterface().run(args)


run = cli

if __name__ == '__main__':
    run()
