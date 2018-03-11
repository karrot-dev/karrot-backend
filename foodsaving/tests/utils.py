from contextlib import contextmanager
from unittest.mock import Mock

from channels.test import WSClient
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase


# Mostly based on this nice persons article:
#   https://www.caktusgroup.com/blog/2016/02/02/writing-unit-tests-django-migrations/
class TestMigrations(TestCase):
    @property
    def app(self):
        return apps.get_containing_app_config(type(self).__module__).name

    migrate_from = None
    migrate_to = None

    def setUp(self):
        assert self.migrate_from and self.migrate_to, \
            "TestCase '{}' must define migrate_from and migrate_to properties".format(type(self).__name__)

        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        # Reverse to the original migration
        executor.migrate(self.migrate_from)

        self.setUpBeforeMigration(old_apps)

        # Run the migration to test
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()  # reload.
        executor.migrate(self.migrate_to)

        self.apps = executor.loader.project_state(self.migrate_to).apps

    def setUpBeforeMigration(self, apps):
        pass


class ExtractPaginationMixin(object):
    def get_results(self, *args, **kwargs):
        """Overrides response.data to remove the pagination control in tests"""
        response = self.client.get(*args, **kwargs)
        if 'results' in response.data:
            response.data = response.data['results']
        return response


class ReceiveAllWSClient(WSClient):
    def receive_all(self, *args, **kwargs):
        while True:
            response = self.receive(*args, **kwargs)
            if response is None:
                break
            yield response


@contextmanager
def signal_handler_for(signal):
    handler = Mock()
    try:
        signal.connect(handler)
        yield handler
    finally:
        signal.disconnect(handler)
