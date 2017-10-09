import threading

from rest_framework import status

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.stores.serializers import PickupDateJoinSerializer
from foodsaving.tests.liveserver import MultiprocessTestCase
from foodsaving.tests.utils import add_delay, sessions
from foodsaving.users.factories import UserFactory


class Fixture():
    def __init__(self, members=1):
        # pickup date for group with one member and one store
        self.members = []
        for m in range(members):
            self.members.append(UserFactory())
        self.group = GroupFactory(members=self.members)
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store, max_collectors=1)

        self.pickup_url = '/api/pickup-dates/{}/'.format(self.pickup.id)
        self.join_url = self.pickup_url + 'add/'
        self.remove_url = self.pickup_url + 'remove/'


class TestPickupDatesAPILive(MultiprocessTestCase):
    worker_threads = 4
    worker_context = [add_delay((PickupDateJoinSerializer, 'update')), ]

    def test_single_user_joins_pickup_concurrently(self):
        data = Fixture(members=1)
        member = data.members[0]

        with sessions((self.live_server_url, member.email, member.display_name) for _ in range(4)) as clients:
            responses = []

            def do_requests(client):
                responses.append(client.post(data.join_url))

            threads = [threading.Thread(target=do_requests, kwargs={'client': c}) for c in clients]
            [t.start() for t in threads]
            [t.join() for t in threads]

            self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))
            self.assertEqual(len(clients) - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))
            self.assertEqual(data.pickup.collectors.count(), 1)

    def test_many_users_join_pickup_concurrently(self):
        data = Fixture(members=4)

        with sessions((self.live_server_url, member.email, member.display_name) for member in data.members) as clients:
            responses = []

            def do_requests(client):
                responses.append(client.post(data.join_url))

            threads = [threading.Thread(target=do_requests, kwargs={'client': c}) for c in clients]
            [t.start() for t in threads]
            [t.join() for t in threads]

            self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))
            self.assertEqual(len(clients) - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))
            self.assertEqual(data.pickup.collectors.count(), 1)

    def test_single_user_leaves_pickup_concurrently(self):
        data = Fixture(members=1)
        member = data.members[0]
        data.pickup.collectors.add(member)

        with sessions((self.live_server_url, member.email, member.display_name) for _ in range(4)) as clients:
            responses = []

            def do_requests(client):
                responses.append(client.post(data.remove_url))

            threads = [threading.Thread(target=do_requests, kwargs={'client': c}) for c in clients]
            [t.start() for t in threads]
            [t.join() for t in threads]

            self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))
            self.assertEqual(len(clients) - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))

    def test_destroy_pickup_concurrently(self):
        data = Fixture(members=1)
        member = data.members[0]

        with sessions((self.live_server_url, member.email, member.display_name) for _ in range(4)) as clients:
            responses = []

            def do_requests(client):
                responses.append(client.delete(data.pickup_url))

            threads = [threading.Thread(target=do_requests, kwargs={'client': c}) for c in clients]
            [t.start() for t in threads]
            [t.join() for t in threads]

            self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))
            self.assertEqual(len(clients) - 1, sum(1 for r in responses if r.status_code == status.HTTP_404_NOT_FOUND))
