import os

from django.conf import settings
from django.test import TestCase, override_settings

from karrot.groups.factories import GroupFactory
from karrot.offers.factories import OfferFactory
from karrot.utils.frontend_urls import absolute_url, offer_image_url, group_photo_url, group_photo_or_karrot_logo_url, \
    karrot_logo_url

photo_path = os.path.join(os.path.dirname(__file__), './photo.jpg')


class TestAbsoluteURL(TestCase):
    @override_settings(HOSTNAME='https://localhost:8000')
    def test_path(self):
        self.assertEqual(absolute_url('/foo'), 'https://localhost:8000/foo')

    def test_existing_absolute_url(self):
        self.assertEqual(absolute_url('http://example.com/yay'), 'http://example.com/yay')
        self.assertEqual(absolute_url('https://example.com/yay'), 'https://example.com/yay')

    def test_group_photo_url(self):
        group = GroupFactory(photo=photo_path)
        url = group_photo_url(group)
        self.assertEqual(
            url,
            '{hostname}/api/groups-info/{id}/photo/'.format(
                hostname=settings.HOSTNAME,
                id=group.id,
            ),
        )

    def test_group_photo_url_without_photo(self):
        group = GroupFactory()
        url = group_photo_url(group)
        self.assertEqual(url, None)

    def test_group_photo_or_karrot_logo_url(self):
        group = GroupFactory(photo=photo_path)
        url = group_photo_or_karrot_logo_url(group)
        self.assertEqual(
            url,
            '{hostname}/api/groups-info/{id}/photo/'.format(
                hostname=settings.HOSTNAME,
                id=group.id,
            ),
        )

    def test_group_photo_or_karrot_logo_url_without_photo(self):
        group = GroupFactory()
        url = group_photo_or_karrot_logo_url(group)
        self.assertEqual(url, karrot_logo_url())

    def test_offer_image_url(self):
        offer = OfferFactory(images=[photo_path])
        url = offer_image_url(offer)
        self.assertEqual(url, '{hostname}/api/offers/{id}/image/'.format(
            hostname=settings.HOSTNAME,
            id=offer.id,
        ))

    def test_offer_image_url_without_images(self):
        offer = OfferFactory()
        url = offer_image_url(offer)
        self.assertEqual(url, None)
