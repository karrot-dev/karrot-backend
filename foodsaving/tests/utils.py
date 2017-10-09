from time import sleep

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.test.utils import TestContextDecorator


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


def delay(fn):
    def wrap(*args, **kwargs):
        sleep(0.1)
        return fn(*args, **kwargs)
    return wrap


class add_delay(TestContextDecorator):
    """
    Add short delay before each call to the passed functions.

    Example:
    @add_delay(
        (PickupDateJoinSerializer, 'update'),
        (PickupDateLeaveSerializer, 'update')
    )
    class SomeTestCase(TestCase):
        pass

    This will delay PickupDateJoinSerializer.update and PickupDateLeaveSerializer.update for the duration of the test


    Acts as either a decorator or a context manager. If it's a decorator it
    takes a function and returns a wrapped function. If it's a contextmanager
    it's used with the ``with`` statement. In either event entering/exiting
    are called before and after, respectively, the function/block is executed.
    """
    def __init__(self, *args):
        super().__init__()
        self.fns_to_delay = args
        self._delayed_fns = []

    def enable(self):
        self._delayed_fns = []
        for owner, fn_name in self.fns_to_delay:
            original_fn = getattr(owner, fn_name)
            self._delayed_fns.append((owner, fn_name, original_fn))
            setattr(owner, fn_name, delay(original_fn))

    def disable(self):
        for owner, fn_name, original in self._delayed_fns:
            setattr(owner, fn_name, original)
