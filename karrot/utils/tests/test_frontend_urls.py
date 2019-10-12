from django.test import TestCase

from karrot.utils.frontend_urls import absolute_url


class TestAbsoluteURL(TestCase):
    def test_path(self):
        self.assertEqual(absolute_url('/foo'), 'https://localhost:8000/foo')

    def test_existing_absolute_url(self):
        self.assertEqual(absolute_url('http://example.com/yay'), 'http://example.com/yay')
        self.assertEqual(absolute_url('https://example.com/yay'), 'https://example.com/yay')
