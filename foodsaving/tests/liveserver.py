import unittest
from contextlib import ExitStack
from multiprocessing import current_process

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

    def _pre_setup(self):
        if current_process().daemon:
            # daemon processes can't have children. this limitation imposed by the multiprocessing lib
            def skip_tests(*args, **kwargs):
                raise unittest.SkipTest("MultiprocessTestCase can't run in parallel mode")

            def no_op(*args, **kwargs):
                pass

            self.setUp = skip_tests
            self.setUpClass = no_op
            self.tearDownClass = no_op
            self.tearDown = no_op
            self._post_teardown = no_op
        else:
            super()._pre_setup()
