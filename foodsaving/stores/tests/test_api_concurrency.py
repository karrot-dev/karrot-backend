import threading

from rest_framework import status
from rest_framework.test import APITransactionTestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.users.factories import UserFactory


class TestPickupDatesAPIConcurrently(APITransactionTestCase):
    def test_join_pickup_as_member(self):
        self.url = '/api/pickup-dates/'

        # pickup date for group with one member and one store
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member, ])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)
        self.pickup_url = self.url + str(self.pickup.id) + '/'
        self.join_url = self.pickup_url + 'add/'

        threads = []
        responses = []

        def do_requests():
            self.client.force_login(user=self.member)
            responses.append(self.client.post(self.join_url, format='json'))

        [threads.append(threading.Thread(target=do_requests)) for _ in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        for i in responses:
            print(i.status_code)

        self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK), responses)
        self.assertEqual(9, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN), responses)


