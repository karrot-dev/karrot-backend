from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range
from karrot.history.models import History, HistoryTypus
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestActivitiesTypesAPI(APITestCase):
    def setUp(self):
        self.member = UserFactory()
        self.non_editor_member = UserFactory()
        self.non_member = UserFactory()
        self.group = GroupFactory(members=[self.member, self.non_editor_member])
        self.place = PlaceFactory(group=self.group)
        self.activity_types = list(self.group.activity_types.all())
        self.activity_type = self.activity_types[0]

        # remove all roles
        GroupMembership.objects.filter(group=self.group, user=self.non_editor_member).update(roles=[])

    def activity_type_data(self, extra=None):
        if extra is None:
            extra = {}
        return {
            'group': self.group.id,
            'name': 'MyNiceNewType',
            'colour': 'FF0000',
            'icon': 'fa fa-circle',
            'has_feedback': True,
            'has_feedback_weight': False,
            'feedback_icon': 'fa fa-reply',
            **extra,
        }

    def activity_data(self, extra=None):
        if extra is None:
            extra = {}
        return {
            'date': to_range(timezone.now() + relativedelta(days=2)).as_list(),
            'max_participants': 5,
            'place': self.place.id,
            **extra,
        }

    def test_can_list(self):
        self.client.force_login(user=self.member)
        response = self.client.get('/api/activity-types/')
        self.assertEqual(len(response.data), 4)

    def test_can_create(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/activity-types/', self.activity_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_create_if_not_editor(self):
        self.client.force_login(user=self.non_editor_member)
        response = self.client.post('/api/activity-types/', self.activity_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_for_group_if_not_member(self):
        self.client.force_login(user=self.member)
        other_group = GroupFactory()
        response = self.client.post(
            '/api/activity-types/', self.activity_type_data({
                'group': other_group.id,
            }), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_create_activity_for_custom_type(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/activity-types/', self.activity_type_data(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        activity_response = self.client.post(
            '/api/activities/', self.activity_data({
                'activity_type': response.data['id'],
            }), format='json'
        )
        self.assertEqual(activity_response.status_code, status.HTTP_201_CREATED, activity_response.data)

    def test_can_modify(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            f'/api/activity-types/{self.activity_type.id}/', {
                'colour': 'ABABAB',
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cannot_modify_if_not_editor(self):
        self.client.force_login(user=self.non_editor_member)
        response = self.client.patch(
            f'/api/activity-types/{self.activity_type.id}/', {
                'colour': 'ABABAB',
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_modify_group(self):
        self.client.force_login(user=self.member)
        other_group = GroupFactory()
        response = self.client.patch(
            f'/api/activity-types/{self.activity_type.id}/', {
                'group': other_group.id,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_delete(self):
        self.client.force_login(user=self.member)
        activity_type = self.activity_types[0]
        response = self.client.delete(f'/api/activity-types/{activity_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

    def test_cannot_delete_with_activities(self):
        self.client.force_login(user=self.member)
        activity_type = self.activity_types[0]
        activity = ActivityFactory(activity_type=activity_type)
        response = self.client.delete(f'/api/activity-types/{activity_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        # make sure we can delete it if we get rid of the activity
        activity.delete()
        response = self.client.delete(f'/api/activity-types/{activity_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

    def test_adds_history_entry_on_create(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/activity-types/', self.activity_type_data(), format='json')
        history = History.objects.filter(typus=HistoryTypus.ACTIVITY_TYPE_CREATE).last()
        self.assertEqual(history.after['id'], response.data['id'], response.data)

    def test_adds_history_entry_on_modify(self):
        self.client.force_login(user=self.member)
        activity_type = self.activity_types[0]
        response = self.client.patch(
            f'/api/activity-types/{activity_type.id}/', {
                'colour': 'ABABAB',
            }, format='json'
        )
        history = History.objects.filter(typus=HistoryTypus.ACTIVITY_TYPE_MODIFY).last()
        self.assertEqual(history.after['id'], response.data['id'], response.data)
        self.assertEqual(history.payload, {'colour': 'ABABAB'})

    def test_adds_updated_reason_to_history(self):
        self.client.force_login(user=self.member)
        activity_type = self.activity_types[0]
        response = self.client.patch(
            f'/api/activity-types/{activity_type.id}/', {
                'colour': 'ACABAB',
                'updated_message': 'because it was a horrible colour before',
            },
            format='json'
        )
        history = History.objects.filter(typus=HistoryTypus.ACTIVITY_TYPE_MODIFY).last()
        self.assertEqual(history.after['id'], response.data['id'])
        self.assertEqual(history.message, 'because it was a horrible colour before')

    def test_adds_history_entry_on_delete(self):
        self.client.force_login(user=self.member)
        activity_type = self.activity_types[0]
        self.client.delete(f'/api/activity-types/{activity_type.id}/')
        history = History.objects.filter(typus=HistoryTypus.ACTIVITY_TYPE_DELETE).last()
        self.assertEqual(history.before['id'], activity_type.id)
