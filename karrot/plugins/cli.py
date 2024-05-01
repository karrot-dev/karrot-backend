import click

from karrot.plugins.registry import plugins


@click.group(name="plugin")
def plugin_cli():
    pass


@plugin_cli.command(name="list")
def plugin_list():
    for name, _ in plugins.items():
        print(name)
