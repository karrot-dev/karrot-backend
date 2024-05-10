from importlib import import_module
from os import walk
from os.path import dirname, join

from django.test import TestCase

import karrot


def iter_sources(root_module_path, pysuffix=".py"):
    def is_source(_):
        return _.endswith(pysuffix) and not _.startswith("__init__")

    for root, _, leaves in walk(root_module_path):
        for leaf in filter(is_source, leaves):
            yield join(root, leaf)


def iter_modules(root_module_path, excludes=None):
    def is_excluded(module):
        return excludes and any(module.startswith(exclude) for exclude in excludes)

    def source_to_module(_, pysuffix=".py"):
        _ = _[len(dirname(root_module_path)) + 1 : -len(pysuffix)]
        _ = _.replace("/", ".")
        return _

    for source in iter_sources(root_module_path):
        module = source_to_module(source)
        if not is_excluded(module):
            yield module


class PythonIsValidTestCase(TestCase):
    def test_all_modules_import_cleanly(self):
        for module in iter_modules(
            root_module_path=karrot.__path__[0],
            excludes={
                "karrot.tests.integration.test_integration",  # integration test runner has side-effects
            },
        ):
            try:
                import_module(module)
            except Exception as e:  # noqa: BLE001
                self.fail(f"{module} did not import cleanly: {e.args[0]}")
