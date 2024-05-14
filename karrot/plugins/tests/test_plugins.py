from os.path import isfile, join

from karrot.plugins.registry import plugins
from karrot.plugins.tests.testcases import PluginTestCase


class TestSimpleFrontendPlugin(PluginTestCase):
    plugin_name = "simple-frontend-plugin"

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
        response = await self.request_asset(entry)
        self.assertEqual(response["status"], 200)
        self.assertIn((b"content-type", b"text/javascript; charset=utf-8"), response["headers"])
        with open(asset_file_path, "rb") as asset_file:
            self.assertEqual(response["body"], asset_file.read())

    async def test_css_asset(self):
        css_entry = self.plugin.frontend_plugin.css_entries[0]
        asset_dir = self.plugin.frontend_plugin.asset_dir
        asset_file_path = join(asset_dir, css_entry)
        response = await self.request_asset(css_entry)
        self.assertEqual(response["status"], 200)
        self.assertIn((b"content-type", b"text/css; charset=utf-8"), response["headers"])
        with open(asset_file_path, "rb") as asset_file:
            self.assertEqual(response["body"], asset_file.read())

    async def test_invalid_asset_fails(self):
        response = await self.request_asset("invalid.js")
        self.assertEqual(response["status"], 404)
