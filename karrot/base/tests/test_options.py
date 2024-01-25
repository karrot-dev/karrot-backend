from tempfile import NamedTemporaryFile
from unittest.mock import patch

from django.test import TestCase

from config.options import get_options


class TestOptions(TestCase):
    @patch.dict("os.environ", {"DATABASE_PASSWORD": "a-test-password"})
    def test_reads_from_environ(self):
        options = get_options()
        self.assertEqual(options["DATABASE_PASSWORD"], "a-test-password")

    def test_reads_from_file(self):
        with NamedTemporaryFile() as tmpfile:
            tmpfile.write(b"a-test-password-in-a-file\n")
            tmpfile.seek(0)
            with patch.dict("os.environ", {"DATABASE_PASSWORD_FILE": tmpfile.name}):
                options = get_options()
                self.assertEqual(options["DATABASE_PASSWORD"], "a-test-password-in-a-file")
