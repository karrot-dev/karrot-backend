import os

import click
from uvicorn.workers import UvicornWorker
from gunicorn.app.base import BaseApplication
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


def server_daphne():
    """Run server using daphne"""

    args = []
    args += ['--proxy-headers']

    if settings.REQUEST_TIMEOUT_SECONDS:
        args += ['--http-timeout', str(settings.REQUEST_TIMEOUT_SECONDS)]

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


def server_uvicorn():
    """Run server using uvicorn worker and gunicorn manager
    
    As recommended by:
    https://www.uvicorn.org/deployment/#using-a-process-manager

    See available settings:
    https://docs.gunicorn.org/en/stable/settings.html
    """

    options = {
        'workers': settings.LISTEN_CONCURRENCY,
        'worker_class': 'karrot.cli.KarrotUvicornWorker',
    }

    if settings.REQUEST_TIMEOUT_SECONDS:
        options['timeout'] = settings.REQUEST_TIMEOUT_SECONDS

    bind = []

    if settings.LISTEN_FD:
        bind.append(f"fd://{settings.LISTEN_FD}")

    if settings.LISTEN_HOST:
        if settings.LISTEN_PORT:
            bind.append(':'.join([
                settings.LISTEN_HOST,
                settings.LISTEN_PORT,
            ]))
        else:
            bind.append(settings.LISTEN_HOST)
    elif settings.LISTEN_PORT:
        bind.append(f"127.0.0.1:{settings.LISTEN_PORT}")

    if settings.LISTEN_SOCKET:
        bind.append(f"unix:{settings.LISTEN_SOCKET}")

    if len(bind) > 0:
        options['bind'] = bind

    from config.asgi import application
    KarrotGunicornApplication(application, options).run()


class KarrotGunicornApplication(BaseApplication):
    """Allows us to run gunicorn application programmatically

    See:
    https://docs.gunicorn.org/en/stable/custom.html
    """
    def __init__(self, app, options):
        self.application = app
        self.options = options or {}
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items() if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


class KarrotUvicornWorker(UvicornWorker):
    """A uvicorn worker with the settings as we want
    
    See available settings:
    https://www.uvicorn.org/settings/
    """
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # gets rid of "'lifespan' protocol appears unsupported." message
        self.config.lifespan = 'off'

        # settings suitable for proxy deployment, e.g. nginx, see:
        # https://www.uvicorn.org/deployment/#running-behind-nginx
        self.config.proxy_headers = True
        self.config.forwarded_allow_ips = '*'


run = cli

if __name__ == '__main__':
    run()
