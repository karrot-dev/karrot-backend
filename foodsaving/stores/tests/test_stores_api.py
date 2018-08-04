from copy import deepcopy
from itertools import groupby
from operator import attrgetter
from random import choice

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupStatus
from foodsaving.pickups.factories import PickupDateSeriesFactory, PickupDateFactory, FeedbackFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.stores.models import StoreStatus
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class TestStoresAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/stores/'

        # group with two members and one store
        self.member = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(editors=[self.member, self.member2])
        self.store = StoreFactory(group=self.group)
        self.store_url = self.url + str(self.store.id) + '/'

        # not a member
        self.user = UserFactory()

        # another store for above group
        self.store_data = {
            'name': faker.name(),
            'description': faker.name(),
            'group': self.group.id,
            'address': faker.address(),
            'latitude': faker.latitude(),
            'longitude': faker.longitude()
        }

        # another group
        self.different_group = GroupFactory(editors=[self.member2])

    def test_create_store(self):
        response = self.client.post(self.url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_store_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_store_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], self.store_data['name'])

    def test_create_store_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_store_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        self.client.post(self.url, self.store_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_store_with_short_name_fails(self):
        self.client.force_login(user=self.member)
        data = deepcopy(self.store_data)
        data['name'] = 's'
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_stores(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_stores_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_stores_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_stores(self):
        response = self.client.get(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_stores_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_stores_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patch_store(self):
        response = self.client.patch(self.store_url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_store_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.patch(self.store_url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_store_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_edit_store_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.store_url, self.store_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_store_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        self.client.patch(self.store_url, self.store_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_valid_status(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, {'status': 'active'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_status(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, {'status': 'foobar'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_group_as_member_in_one(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, {'group': self.different_group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_group_as_member_in_both(self):
        self.client.force_login(user=self.member2)
        response = self.client.patch(self.store_url, {'group': self.different_group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.patch(self.store_url, {'group': self.group.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_stores(self):
        response = self.client.delete(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_stores_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.delete(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_stores_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.delete(self.store_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestStoreChangesPickupDateSeriesAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):

        self.now = timezone.now()
        self.url = '/api/stores/'
        self.member = UserFactory()
        self.group = GroupFactory(editors=[self.member])
        self.store = StoreFactory(group=self.group)
        self.store_url = self.url + str(self.store.id) + '/'
        self.series = PickupDateSeriesFactory(max_collectors=3, store=self.store)
        self.series.update_pickup_dates(start=lambda: self.now)

    def test_reduce_weeks_in_advance(self):
        self.client.force_login(user=self.member)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.patch(self.store_url, {'weeks_in_advance': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weeks_in_advance'], 2)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertLessEqual(parse(_['date']), self.now + relativedelta(weeks=2, hours=1))

    def test_increase_weeks_in_advance(self):
        self.client.force_login(user=self.member)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date']) for _ in response.data]

        response = self.client.patch(self.store_url, {'weeks_in_advance': 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weeks_in_advance'], 10)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertGreater(len(response.data), len(original_dates))
        for return_date in response.data:
            self.assertLessEqual(parse(return_date['date']), self.now + relativedelta(weeks=10))

    def test_set_weeks_to_invalid_value(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, {'weeks_in_advance': 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_set_store_active_status_updates_pickup_dates(self):
        self.store.status = StoreStatus.ARCHIVED.value
        self.store.save()
        self.store.pickup_dates.all().delete()
        self.client.force_login(user=self.member)
        response = self.client.patch(self.store_url, {'status': StoreStatus.ACTIVE.value}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(self.store.pickup_dates.count(), 0)


class TestStoreStatisticsAPI(APITestCase):
    def test_store_statistics(self):
        user = UserFactory()
        self.client.force_login(user=user)
        group = GroupFactory(editors=[user])
        store = StoreFactory(group=group)

        response = self.client.get('/api/stores/{}/statistics/'.format(store.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            'feedback_count': 0,
            'feedback_weight': 0,
            'pickups_done': 0,
        })

        one_day_ago = timezone.now() - relativedelta(days=1)

        users = [UserFactory() for _ in range(9)]
        pickups = [
            PickupDateFactory(
                store=store,
                date=one_day_ago,
                collectors=users,
                done_and_processed=True,
            ) for _ in range(3)
        ]
        feedback = [FeedbackFactory(about=choice(pickups), given_by=u) for u in users]

        # calculate weight from feedback
        feedback.sort(key=attrgetter('about.id'))
        weight = 0
        for _, fs in groupby(feedback, key=attrgetter('about.id')):
            len_list = [f.weight for f in fs]
            weight += float(sum(len_list)) / len(len_list)
        weight = round(weight)

        response = self.client.get('/api/stores/{}/statistics/'.format(store.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {
                'feedback_count': len(feedback),
                'feedback_weight': weight,
                'pickups_done': len(pickups),
            }
        )
