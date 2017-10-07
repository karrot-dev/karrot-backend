from contextlib import ExitStack

from channels.test import ChannelLiveServerTestCase
from channels.worker import Worker


def apply_context(context_managers, fn):
    def wrap(*args, **kwargs):
        with ExitStack() as stack:
            for manager in context_managers:
                stack.enter_context(manager)
            return fn(*args, **kwargs)
    return wrap


class MultiprocessTestCase(ChannelLiveServerTestCase):
    """
    Provides a test environment where HTTP workers run separated from the test.
    This allows for concurrency tests.

    Workers are not affected by (most) test decorators or context managers, as workers run in a separate process.
    To work around this, this class allows to set context managers in a `worker_context` attribute
    """
    worker_context = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._original_channels_worker_run = Worker.run
        Worker.run = apply_context(cls.worker_context, Worker.run)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        Worker.run = cls._original_channels_worker_run
