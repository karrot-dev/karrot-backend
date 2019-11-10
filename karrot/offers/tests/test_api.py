import json
import os
from io import StringIO

from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.offers.factories import OfferFactory
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker

image_path = os.path.join(os.path.dirname(__file__), './photo.jpg')


def encode_offer_data(data):
    post_data = {}
    for index, image in enumerate(data.get('images', [])):
        image_file = image.pop('image', None)
        if image_file:
            post_data['images.{}.image'.format(index)] = image_file
    data_file = StringIO(json.dumps(data))
    setattr(data_file, 'content_type', 'application/json')
    post_data['document'] = data_file
    return post_data


class TestOffersAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])

    def test_fetch_offer(self):
        self.client.force_login(user=self.user)
        offer = OfferFactory(user=self.user, group=self.group)
        response = self.client.get('/api/offers/{}/'.format(offer.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], offer.name)

    def test_create_offer(self):
        self.client.force_login(user=self.user)
        with open(image_path, 'rb') as image_file:
            data = {
                'name': faker.name(),
                'description': faker.text(),
                'group': self.group.id,
                'images': [{
                    'position': 0,
                    'image': image_file
                }],
            }
            response = self.client.post('/api/offers/', data=encode_offer_data(data))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data['name'], data['name'])
            self.assertTrue('full_size' in response.data['images'][0]['image_urls'])

    def test_update_offer(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path])
        self.client.force_login(user=self.user)
        data = {
            'name': 'woo',
        }
        response = self.client.patch('/api/offers/{}/'.format(offer.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['name'], data['name'])

    def test_add_image(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path])
        self.client.force_login(user=self.user)
        with open(image_path, 'rb') as image_file:
            data = {
                'images': [{
                    'position': 1,
                    'image': image_file
                }],
            }
            response = self.client.patch(
                '/api/offers/{}/'.format(offer.id), encode_offer_data(data), format='multipart'
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data['images']), 2)

    def test_remove_image(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path, image_path])
        self.client.force_login(user=self.user)
        data = {
            'images': [{
                'id': offer.images.first().id,
                '_removed': True
            }],
        }
        response = self.client.patch(
            '/api/offers/{}/'.format(offer.id), encode_offer_data(data), format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['images']), 1)
