import threading

import random
from rest_framework import status

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.api import PickupDateViewSet
from foodsaving.stores.factories import StoreFactory, PickupDateFactory, PickupDateSeriesFactory
from foodsaving.stores.serializers import PickupDateJoinSerializer, PickupDateLeaveSerializer, PickupDateSerializer
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

    @property
    def pickup_url(self):
        return '/api/pickup-dates/{}/'.format(self.pickup.id)

    @property
    def join_url(self):
        return self.pickup_url + 'add/'

    @property
    def remove_url(self):
        return self.pickup_url + 'remove/'


class TestPickupDatesAPILive(MultiprocessTestCase):
    worker_threads = 4
    worker_context = [add_delay(
        (PickupDateJoinSerializer, 'update'),
        (PickupDateLeaveSerializer, 'update'),
        (PickupDateViewSet, 'perform_destroy'),
        (PickupDateSerializer, 'update'),
    ), ]
    '''
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

    def test_destroy_and_join_pickup_concurrently(self):
        data = Fixture(members=4)

        with sessions((self.live_server_url, member.email, member.display_name) for member in data.members) as clients:
            responses = []

            def do_requests(client, id):
                if id == 0:
                    r = client.delete(data.pickup_url)
                else:
                    r = client.post(data.join_url)
                responses.append(r)
            for _ in range(3):
                threads = [threading.Thread(target=do_requests, kwargs={'id': id, 'client': c}) for id, c in enumerate(clients)]
                random.shuffle(threads)
                [t.start() for t in threads]
                [t.join() for t in threads]

                self.assertFalse(any(status.is_server_error(r.status_code) for r in responses))
                self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))

                responses = []
                data.pickup.collectors.clear()
                data.pickup.deleted = False
                data.pickup.save()
    '''
    def test_delete_series_and_join_pickup_concurrently(self):
        data = Fixture(members=4)

        with sessions((self.live_server_url, member.email, member.display_name) for member in data.members) as clients:
            responses = []

            def do_requests(client, id, series_id, join_url):
                if id == 0:
                    r = client.delete('/api/pickup-date-series/{}/'.format(series_id))
                else:
                    r = client.post(join_url)
                responses.append(r)

            for _ in range(3):
                print('round', _)
                series = PickupDateSeriesFactory(store=data.store)
                data.pickup = PickupDateFactory(series=series, store=data.store)

                threads = [threading.Thread(target=do_requests, kwargs={'id': id, 'client': c, 'series_id': series.id, 'join_url': data.join_url}) for id, c in enumerate(clients)]
                random.shuffle(threads)
                [t.start() for t in threads]
                [t.join() for t in threads]

                for r in responses:
                    print(r)

                # self.assertFalse(any(status.is_server_error(r.status_code) for r in responses))
                # self.assertEqual(1, sum(1 for r in responses if status.is_success(r.status_code)))

                responses = []



    """
    delete store + join/leave/create/modify pickup
    remove series + join pickup
    """
