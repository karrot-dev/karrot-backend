from copy import deepcopy
from itertools import groupby
from operator import attrgetter
from random import choice

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupStatus
from karrot.activities.factories import ActivitySeriesFactory, ActivityFactory, FeedbackFactory
from karrot.activities.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class TestPlacesAPI(APITestCase, ExtractPaginationMixin):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/api/places/'

        # group with two members and one place
        cls.member = UserFactory()
        cls.member2 = UserFactory()
        cls.group = GroupFactory(members=[cls.member, cls.member2])
        cls.place = PlaceFactory(group=cls.group)
        cls.place_url = cls.url + str(cls.place.id) + '/'

        # not a member
        cls.user = UserFactory()

        # another place for above group
        cls.place_data = {
            'name': faker.name(),
            'description': faker.name(),
            'group': cls.group.id,
            'address': faker.address(),
            'latitude': faker.latitude(),
            'longitude': faker.longitude(),
            'status': cls.group.place_statuses.get(name='Created').id,
            'place_type': cls.group.place_types.get(name='Store').id,
        }

        # another group
        cls.different_group = GroupFactory(members=[cls.member2])

    def setUp(self):
        self.group.refresh_from_db()

    def test_create_place(self):
        response = self.client.post(self.url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_place_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_place_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], self.place_data['name'])

    def test_create_place_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_place_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_place_with_short_name_fails(self):
        self.client.force_login(user=self.member)
        data = deepcopy(self.place_data)
        data['name'] = 's'
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_places(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_places_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_places_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_places(self):
        response = self.client.get(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_places_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_places_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patch_place(self):
        response = self.client.patch(self.place_url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_place_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.patch(self.place_url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_place_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.place_url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_edit_place_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.place_url, self.place_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_place_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        self.client.patch(self.place_url, self.place_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_valid_status(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.place_url, {'status': self.group.place_statuses.get(name='Active').id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_status(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.place_url, {'status': 'foobar'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_group_as_member_in_one(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.place_url, {'group': self.different_group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_group_as_member_in_both(self):
        self.client.force_login(user=self.member2)
        response = self.client.patch(self.place_url, {'group': self.different_group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.patch(self.place_url, {'group': self.group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_places(self):
        response = self.client.delete(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_places_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.delete(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_places_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.delete(self.place_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_subscribe_and_get_conversation(self):
        self.client.force_login(user=self.member)
        response = self.client.get('/api/places/{}/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['is_subscribed'])

        response = self.client.post('/api/places/{}/subscription/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.client.get('/api/places/{}/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['is_subscribed'])

        response = self.client.get('/api/places/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data[0]['is_subscribed'])

        response = self.client.get('/api/places/{}/conversation/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(self.member.id, response.data['participants'])
        self.assertEqual(response.data['type'], 'place')
        self.assertEqual(len(response.data['participants']), 1)

        # post message in conversation
        data = {'conversation': response.data['id'], 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unsubscribe(self):
        self.place.placesubscription_set.create(user=self.member)

        self.client.force_login(user=self.member)
        response = self.client.delete('/api/places/{}/subscription/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        # conversation participant also gets deleted
        response = self.client.get('/api/places/{}/conversation/'.format(self.place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn(self.member.id, response.data['participants'])


class TestPlaceChangesActivitySeriesAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):

        self.now = timezone.now()
        self.url = '/api/places/'
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.place_url = self.url + str(self.place.id) + '/'
        self.series = ActivitySeriesFactory(max_participants=3, place=self.place)

    def test_reduce_weeks_in_advance(self):
        self.client.force_login(user=self.member)

        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.patch(self.place_url, {'weeks_in_advance': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weeks_in_advance'], 2)

        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertLessEqual(parse(_['date'][0]), self.now + relativedelta(weeks=2, hours=1))

    def test_increase_weeks_in_advance(self):
        self.client.force_login(user=self.member)

        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        response = self.client.patch(self.place_url, {'weeks_in_advance': 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weeks_in_advance'], 10)

        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertGreater(len(response.data), len(original_dates))
        for return_date in response.data:
            self.assertLessEqual(parse(return_date['date'][0]), self.now + relativedelta(weeks=10))

    def test_set_weeks_to_invalid_low_value(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.place_url, {'weeks_in_advance': 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_set_weeks_to_invalid_high_value(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.place_url, {'weeks_in_advance': 99})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('Do not set more than', response.data['weeks_in_advance'][0])

    def test_set_place_active_status_updates_activities(self):
        self.place.status = self.group.place_statuses.get(name='Archived')
        self.place.save()
        self.place.activities.all().delete()
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.place_url, {'status': self.group.place_statuses.get(name='Active').id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(self.place.activities.count(), 0)


class TestPlaceStatisticsAPI(APITestCase):
    def test_place_statistics_as_average(self):
        user = UserFactory()
        self.client.force_login(user=user)
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)

        response = self.client.get('/api/places/{}/statistics/'.format(place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            'feedback_count': 0,
            'feedback_weight': 0,
            'activities_done': 0,
        })

        one_day_ago = to_range(timezone.now() - relativedelta(days=1))

        users = [UserFactory() for _ in range(9)]
        activities = [
            ActivityFactory(
                place=place,
                date=one_day_ago,
                participants=users,
                is_done=True,
            ) for _ in range(3)
        ]
        feedback = [FeedbackFactory(about=choice(activities), given_by=u) for u in users]

        # calculate weight from feedback
        feedback.sort(key=attrgetter('about.id'))
        weight = 0
        for _, fs in groupby(feedback, key=attrgetter('about.id')):
            len_list = [f.weight for f in fs]
            weight += float(sum(len_list)) / len(len_list)
        weight = round(weight)

        response = self.client.get('/api/places/{}/statistics/'.format(place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {
                'feedback_count': len(feedback),
                'feedback_weight': weight,
                'activities_done': len(activities),
            }
        )
