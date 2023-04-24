from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.offers.factories import OfferFactory
from karrot.users.factories import UserFactory, VerifiedUserFactory
from karrot.utils.tests.fake import faker
from karrot.utils.tests.images import image_path, encode_upload_data


class TestOffersAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.another_user = UserFactory()
        self.group = GroupFactory(members=[self.user, self.another_user])
        self.offer = OfferFactory(user=self.user, group=self.group, images=[image_path])

    def test_offer_image_redirect(self):
        # NOT logged in (as it needs to work in emails)
        response = self.client.get('/api/offers/{}/image/'.format(self.offer.id))
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, self.offer.images.first().image.url)

    def test_fetch_offer(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/offers/{}/'.format(self.offer.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['name'], self.offer.name)

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
            response = self.client.post('/api/offers/', data=encode_upload_data(data))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data['name'], data['name'])
            self.assertTrue('full_size' in response.data['images'][0]['image_urls'])

    def test_create_offer_without_image(self):
        self.client.force_login(user=self.user)
        data = {
            'name': faker.name(),
            'description': faker.text(),
            'group': self.group.id,
            'images': [],
        }
        response = self.client.post('/api/offers/', data=encode_upload_data(data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['name'], data['name'])

    def test_cannot_fetch_another_users_archived_offer(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path], status='archived')
        self.client.force_login(user=self.another_user)
        response = self.client.get('/api/offers/{}/'.format(offer.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_can_fetch_other_users_archived_offer_if_in_the_conversation(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path], status='archived')
        offer.conversation.join(self.another_user)
        self.client.force_login(user=self.another_user)
        response = self.client.get('/api/offers/{}/'.format(offer.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_update_offer(self):
        self.client.force_login(user=self.user)
        data = {
            'name': faker.name(),
        }
        response = self.client.patch('/api/offers/{}/'.format(self.offer.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['name'], data['name'])

    def test_mark_offer_archived(self):
        self.client.force_login(user=self.user)
        response = self.client.post('/api/offers/{}/archive/'.format(self.offer.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'archived')

    def test_mark_offer_archived_as_another_user(self):
        self.client.force_login(user=self.another_user)
        response = self.client.post('/api/offers/{}/archive/'.format(self.offer.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_update_offer_as_another_user(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path])
        self.client.force_login(user=self.another_user)
        data = {
            'name': faker.name(),
        }
        response = self.client.patch('/api/offers/{}/'.format(offer.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

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
                '/api/offers/{}/'.format(offer.id), encode_upload_data(data), format='multipart'
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
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
        response = self.client.patch('/api/offers/{}/'.format(offer.id), encode_upload_data(data), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['images']), 1)

    def test_remove_all_images(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path, image_path])
        self.client.force_login(user=self.user)
        data = {
            'images': [{
                'id': image.id,
                '_removed': True,
            } for image in offer.images.all()],
        }
        response = self.client.patch('/api/offers/{}/'.format(offer.id), encode_upload_data(data), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_reposition_image(self):
        offer = OfferFactory(user=self.user, group=self.group, images=[image_path, image_path])
        self.client.force_login(user=self.user)
        image_id = offer.images.first().id
        new_position = 5
        data = {
            'images': [{
                'id': image_id,
                'position': new_position
            }],
        }
        response = self.client.patch('/api/offers/{}/'.format(offer.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_id = {image['id']: image for image in response.data['images']}
        self.assertEqual(by_id[image_id]['position'], new_position)


@patch('karrot.offers.emails.prepare_email')
class TestOffersTransactionAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.another_user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.another_user])

    def test_create_offer(self, prepare_email):
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
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post('/api/offers/', data=encode_upload_data(data))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            args, kwargs = prepare_email.call_args
            self.assertIsNotNone(kwargs['context']['offer_photo'])


class TestListOffersAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.another_user = UserFactory()
        self.group = GroupFactory(members=[self.user, self.another_user])

    def test_list_offers_by_group(self):
        self.client.force_login(user=self.user)
        another_group = GroupFactory(members=[self.user])  # user is part of this group
        for _ in range(4):
            OfferFactory(user=self.user, group=self.group, images=[image_path])
        for _ in range(2):
            OfferFactory(user=self.user, group=another_group, images=[image_path])

        response = self.client.get('/api/offers/', {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 4)

        response = self.client.get('/api/offers/', {'group': another_group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 2)

    def test_list_offers_by_status(self):
        self.client.force_login(user=self.user)
        for _ in range(4):
            OfferFactory(user=self.user, group=self.group, images=[image_path], status='active')
        for _ in range(2):
            OfferFactory(user=self.user, group=self.group, images=[image_path], status='archived')

        response = self.client.get('/api/offers/', {'status': 'active'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 4)

        response = self.client.get('/api/offers/', {'status': 'archived'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 2)

    def test_cannot_list_offers_for_another_group(self):
        self.client.force_login(user=self.user)
        another_group = GroupFactory()  # user is not part of this group
        for _ in range(2):
            OfferFactory(user=self.user, group=self.group, images=[image_path])
        for _ in range(3):
            OfferFactory(user=self.user, group=another_group, images=[image_path])

        response = self.client.get('/api/offers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 2)

        response = self.client.get('/api/offers/', {'group': another_group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 0)

    def test_cannot_list_another_users_archived_offers(self):
        for _ in range(2):
            OfferFactory(user=self.user, group=self.group, images=[image_path], status='active')
        for _ in range(3):
            OfferFactory(user=self.user, group=self.group, images=[image_path], status='archived')
        self.client.force_login(user=self.another_user)
        response = self.client.get('/api/offers/')
        self.assertEqual(len(response.data['results']), 2)
