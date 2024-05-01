from os.path import basename

import click
import rich
from rich.console import Console
from rich.table import Table

from karrot.plugins.installer import install_plugin, uninstall_plugin
from karrot.plugins.registry import plugins


@click.group(name="plugin")
def plugin_cli():
    pass


@plugin_cli.command(name="list")
def plugin_list():
    table = Table(box=None)

    table.add_column("Name")
    table.add_column("Frontend")
    table.add_column("Backend")

    for plugin_name, plugin in plugins.items():
        table.add_row(
            plugin_name,
            ":heavy_check_mark:" if plugin.frontend_plugin else ":cross_mark:",
            ":heavy_check_mark:" if plugin.backend_plugin else ":cross_mark:",
        )

    console = Console()
    console.print(table)


@plugin_cli.command(name="show")
@click.argument("plugin_name", nargs=1)
def plugin_show(plugin_name):
    print("info about", plugin_name)
    plugin = plugins.get(plugin_name, None)
    if not plugin:
        rich.print(f"[bold]{plugin_name}[/] [red]not found[/]")
        return
    rich.print(f"[bold]{plugin_name}[/]")
    rich.print(
        "frontend", "[green]:heavy_check_mark:[/]" if plugin.frontend_plugin else "[bright_black]:cross_mark:[/]"
    )
    rich.print("backend", "[green]:heavy_check_mark:[/]" if plugin.backend_plugin else "[bright_black]:cross_mark:[/]")


@plugin_cli.command(name="install")
@click.argument("plugin_file", nargs=1)
def plugin_install(plugin_file):
    rich.print(f"Installing [bold]{basename(plugin_file)}[/] ...")
    plugin_name = install_plugin(plugin_file)
    rich.print(f"[bold]{plugin_name}[/]", "[green]:heavy_check_mark: installed[/]")
    rich.print("\n  [black on white]Now restart the app server :hugging_face:[/]")


@plugin_cli.command(name="uninstall")
@click.argument("plugin_name", nargs=1)
def plugin_uninstall(plugin_name):
    uninstall_plugin(plugin_name)
    rich.print(f"[bold]{plugin_name}[/]", "[green]:heavy_check_mark: uninstalled[/]")
    rich.print("\n  [black on white]Now restart the app server :hugging_face:[/]")
