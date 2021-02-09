import os

import click
import uvicorn
from daphne.cli import CommandLineInterface
from django.core import management
from django.conf import settings
import django
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
def cli():
    pass


@click.command()
def check():
    setup()
    management.call_command("check")


@click.command()
def migrate():
    setup()
    management.call_command("migrate", interactive=False)


@click.command()
@click.option('env_files', '--env', help='path to env file', multiple=True)
def config(env_files):
    setup(env_files)
    for key, value in get_options().items():
        print(key + '=' + (value if value else ''))


@click.command()
@click.option('env_files', '--env', help='path to env file', multiple=True)
def server(env_files):
    setup(env_files)
    server_uvicorn() if settings.LISTEN_SERVER == 'uvicorn' else server_daphne()


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
    args = [
        '--ws-protocol',
        'karrot.token',
        '--proxy-headers',
    ]
    # TODO: maybe warn if settings.LISTEN_CONCURRENCY is set.. as it's unsupported here
    if settings.LISTEN_FD:
        args += ['--fd', settings.LISTEN_FD]

    if settings.LISTEN_HOST:
        args += ['--bind', settings.LISTEN_HOST]

    if settings.LISTEN_PORT:
        args += ['--port', settings.LISTEN_PORT]

    if settings.LISTEN_SOCKET:
        args += ['--unix-socket', settings.LISTEN_SOCKET]

    args += ['config.asgi:application']

    CommandLineInterface().run(args)


cli.add_command(check)
cli.add_command(config)
cli.add_command(migrate)
cli.add_command(server)

if __name__ == '__main__':
    cli()
