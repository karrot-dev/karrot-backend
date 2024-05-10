from contextlib import contextmanager
from os.path import dirname, isfile, join, realpath
from tempfile import TemporaryDirectory

from channels.testing import HttpCommunicator
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from config.settings import PLUGIN_ASSETS_PUBLIC_PREFIX
from karrot.plugins.asgi import PluginAssets
from karrot.plugins.registry import initialize_plugins, plugins

PLUGIN_DIR = realpath(join(dirname(__file__), "plugins"))


@contextmanager
def temporary_plugin_dir():
    with TemporaryDirectory() as tmpdir:
        with override_settings(PLUGIN_DIR=tmpdir):
            yield


async def request_asset(path: str) -> dict:
    plugin_assets_app = PluginAssets()
    communicator = HttpCommunicator(
        plugin_assets_app,
        "GET",
        path,
    )
    return await communicator.get_response()


@override_settings(PLUGIN_DIR=PLUGIN_DIR)
class TestSimpleFrontendPlugin(SimpleTestCase):
    def setUp(self):
        initialize_plugins(settings.PLUGIN_DIR)
        self.plugin = plugins.get("simple-frontend-plugin", None)

    def get_asset_path(self, path: str):
        return "/".join([PLUGIN_ASSETS_PUBLIC_PREFIX.rstrip("/"), self.plugin.name, path])

    def test_loads(self):
        self.assertIn("simple-frontend-plugin", plugins.keys())
        self.assertEqual(self.plugin.name, "simple-frontend-plugin")
        self.assertIsNotNone(self.plugin.frontend_plugin)
        self.assertIsNone(self.plugin.backend_plugin)

    async def test_entry_asset(self):
        entry = self.plugin.frontend_plugin.entry
        asset_dir = self.plugin.frontend_plugin.asset_dir
        asset_file_path = join(asset_dir, entry)
        self.assertTrue(isfile(asset_file_path))
        response = await request_asset(self.get_asset_path(entry))
        self.assertEqual(response["status"], 200)
        self.assertIn((b"content-type", b"text/javascript; charset=utf-8"), response["headers"])
        with open(asset_file_path, "rb") as asset_file:
            self.assertEqual(response["body"], asset_file.read())

    async def test_css_asset(self):
        print("self.plugin.frontend_plugin.css_entries", self.plugin.frontend_plugin.css_entries)
        css_entry = self.plugin.frontend_plugin.css_entries[0]
        asset_dir = self.plugin.frontend_plugin.asset_dir
        asset_file_path = join(asset_dir, css_entry)
        response = await request_asset(self.get_asset_path(css_entry))
        self.assertEqual(response["status"], 200)
        self.assertIn((b"content-type", b"text/css; charset=utf-8"), response["headers"])
        with open(asset_file_path, "rb") as asset_file:
            self.assertEqual(response["body"], asset_file.read())

    async def test_invalid_asset_fails(self):
        response = await request_asset(self.get_asset_path("invalid.js"))
        self.assertEqual(response["status"], 404)
