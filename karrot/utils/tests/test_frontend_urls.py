from django.test import TestCase, override_settings

from karrot.utils.frontend_urls import absolute_url


class TestAbsoluteURL(TestCase):
    @override_settings(HOSTNAME='https://localhost:8000')
    def test_path(self):
        self.assertEqual(absolute_url('/foo'), 'https://localhost:8000/foo')

    def test_existing_absolute_url(self):
        self.assertEqual(absolute_url('http://example.com/yay'), 'http://example.com/yay')
        self.assertEqual(absolute_url('https://example.com/yay'), 'https://example.com/yay')
