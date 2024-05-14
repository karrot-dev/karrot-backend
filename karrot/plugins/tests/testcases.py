from os.path import dirname, join, realpath
from shutil import copytree
from tempfile import TemporaryDirectory

from channels.testing import HttpCommunicator
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from config.settings import PLUGIN_ASSETS_PUBLIC_PREFIX
from karrot.plugins.asgi import PluginAssets
from karrot.plugins.registry import Plugin, initialize_plugins, plugins

TEST_PLUGIN_DIR = realpath(join(dirname(__file__), "testcase_plugins"))


@override_settings()  # keep this! check comment in setUp()
class PluginTestCase(SimpleTestCase):
    """Base class for plugin tests

    It will copy the named test plugin from TEST_PLUGIN_DIR to
    a random tmpdir, so it has a clean plugin dir environment.
    """

    plugin_name: str = ""
    plugin: Plugin | None

    def setUp(self):
        tmpdir = TemporaryDirectory()
        self.addCleanup(lambda: tmpdir.cleanup())

        # this should be safe to call as we're operating on a copy of the settings due
        # to the inclusion of @override_settings() on the class which copies the original
        # settings and safely reverts after the test
        settings.PLUGIN_DIR = tmpdir.name

        if self.plugin_name:
            copytree(join(TEST_PLUGIN_DIR, self.plugin_name), join(tmpdir.name, self.plugin_name))

        initialize_plugins(settings.PLUGIN_DIR)
        self.plugin = plugins.get("simple-frontend-plugin", None)
        super().setUp()

    async def request_asset(self, path: str):
        """Use this to request a frontend plugin asset"""

        request_path = "/".join([PLUGIN_ASSETS_PUBLIC_PREFIX.rstrip("/"), self.plugin.name, path])
        plugin_assets_app = PluginAssets()
        communicator = HttpCommunicator(
            plugin_assets_app,
            "GET",
            request_path,
        )
        return await communicator.get_response()
