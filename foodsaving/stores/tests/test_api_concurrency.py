import threading

from rest_framework import status
from rest_framework.test import APITransactionTestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.users.factories import UserFactory


class Fixture():
    def __init__(self, members=1):
        # pickup date for group with one member and one store
        self.members = []
        for m in range(members):
            self.members.append(UserFactory())
        self.group = GroupFactory(members=self.members)
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

        url = '/api/pickup-dates/'
        pickup_url = url + str(self.pickup.id) + '/'
        self.join_url = pickup_url + 'add/'


class TestPickupDatesAPIConcurrently(APITransactionTestCase):
    def test_single_user_joins_pickup_concurrently(self):
        data = Fixture(members=1)

        threads = []
        responses = []

        def do_requests():
            self.client.force_login(user=data.members[0])
            responses.append(self.client.post(data.join_url, format='json'))

        requests = 6
        [threads.append(threading.Thread(target=do_requests)) for _ in range(requests)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        self.assertEqual(requests - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))

    def test_many_users_join_pickup_concurrently(self):
        data = Fixture(members=4)

        threads = []
        responses = []

        def do_requests(member):
            self.client.force_login(user=member)
            responses.append(self.client.post(data.join_url, format='json'))

        requests = 4
        [threads.append(threading.Thread(
            target=do_requests,
            kwargs={'member': data.members[id]})
        ) for id in range(requests)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        self.assertEqual(requests - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))


