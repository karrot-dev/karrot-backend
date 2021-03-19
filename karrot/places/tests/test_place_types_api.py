from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.history.models import HistoryTypus, History
from karrot.places.factories import PlaceFactory, PlaceTypeFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class TestPlaceTypesAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.non_editor_member = UserFactory()
        self.non_member = UserFactory()
        self.group = GroupFactory(members=[self.member, self.non_editor_member])
        self.place = PlaceFactory(group=self.group)
        self.place_types = [PlaceTypeFactory(group=self.group) for _ in range(3)]
        self.place_type = self.place_types[0]

        # remove all roles
        GroupMembership.objects.filter(group=self.group, user=self.non_editor_member).update(roles=[])

    def test_can_list(self):
        self.client.force_login(user=self.member)
        response = self.client.get('/api/place-types/')
        self.assertEqual(len(response.data), len(self.place_types) + 1)  # 1 is a default one that comes for free!

    def test_can_create(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/place-types/', self.place_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_create_if_not_editor(self):
        self.client.force_login(user=self.non_editor_member)
        response = self.client.post('/api/place-types/', self.place_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_for_group_if_not_member(self):
        self.client.force_login(user=self.member)
        other_group = GroupFactory()
        response = self.client.post(
            '/api/place-types/', self.place_type_data({
                'group': other_group.id,
            }), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_create_place_for_custom_type(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/place-types/', self.place_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        place_response = self.client.post(
            '/api/places/', self.place_data({
                'place_type': response.data['id'],
            }), format='json'
        )
        self.assertEqual(place_response.status_code, status.HTTP_201_CREATED, place_response.data)

    def test_can_modify(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            f'/api/place-types/{self.place_type.id}/', {
                'icon': 'fas fa-changed',
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cannot_modify_if_not_editor(self):
        self.client.force_login(user=self.non_editor_member)
        response = self.client.patch(
            f'/api/place-types/{self.place_type.id}/', {
                'icon': 'fas fa-changed',
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_modify_group(self):
        self.client.force_login(user=self.member)
        other_group = GroupFactory()
        response = self.client.patch(
            f'/api/place-types/{self.place_type.id}/', {
                'group': other_group.id,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_delete(self):
        self.client.force_login(user=self.member)
        response = self.client.delete(f'/api/place-types/{self.place_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

    def test_cannot_delete_with_places(self):
        self.client.force_login(user=self.member)
        place = PlaceFactory(place_type=self.place_type)
        response = self.client.delete(f'/api/place-types/{self.place_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        # make sure we can delete it if we get rid of the activity
        place.delete()
        response = self.client.delete(f'/api/place-types/{self.place_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

    def test_adds_history_entry_on_create(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/place-types/', self.place_type_data(), format='json')
        history = History.objects.filter(typus=HistoryTypus.PLACE_TYPE_CREATE).last()
        self.assertEqual(history.after['id'], response.data['id'], response.data)

    def test_adds_history_entry_on_modify(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            f'/api/place-types/{self.place_type.id}/', {
                'icon': 'fas fa-changed',
            }, format='json'
        )
        history = History.objects.filter(typus=HistoryTypus.PLACE_TYPE_MODIFY).last()
        self.assertEqual(history.after['id'], response.data['id'], response.data)
        self.assertEqual(history.payload, {'icon': 'fas fa-changed'})

    def test_adds_updated_reason_to_history(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            f'/api/place-types/{self.place_type.id}/', {
                'icon': 'fas fa-changed',
                'updated_message': 'because it was a horrible icon before',
            },
            format='json'
        )
        history = History.objects.filter(typus=HistoryTypus.PLACE_TYPE_MODIFY).last()
        self.assertEqual(history.after['id'], response.data['id'])
        self.assertEqual(history.message, 'because it was a horrible icon before')

    def test_adds_history_entry_on_delete(self):
        self.client.force_login(user=self.member)
        self.client.delete(f'/api/place-types/{self.place_type.id}/')
        history = History.objects.filter(typus=HistoryTypus.PLACE_TYPE_DELETE).last()
        self.assertEqual(history.before['id'], self.place_type.id)

    def place_type_data(self, extra=None):
        if extra is None:
            extra = {}
        return {
            'name': 'NiceCustomType',
            'icon': 'fa fa-circle',
            'group': self.group.id,
            **extra,
        }

    def place_data(self, extra=None):
        if extra is None:
            extra = {}
        return {
            'name': faker.sentence(nb_words=4),
            'group': self.group.id,
            'status': self.group.place_statuses.order_by('?').first().id,
            **extra,
        }
