import threading

from rest_framework import status
from rest_framework.test import APITransactionTestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.stores.factories import StoreFactory, PickupDateFactory
from foodsaving.stores.serializers import PickupDateJoinSerializer
from foodsaving.stores.tests.liveserver import ChannelLiveServerTestCase
from foodsaving.stores.tests.shared import CSRFSession
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

        url = '/api/pickup-dates/'
        pickup_url = url + str(self.pickup.id) + '/'
        self.join_url = pickup_url + 'add/'
        self.remove_url = pickup_url + 'remove/'


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
            kwargs={'member': data.members[id]}
        )) for id in range(requests)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        self.assertEqual(requests - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))


def delay(fn):
    def wrap(*args, **kwargs):
        # print('sleeping!')
        # sleep(0.5)
        return fn(*args, **kwargs)
    return wrap


class TestPickupDatesAPILive(ChannelLiveServerTestCase):
    worker_threads = 1

    @classmethod
    def _setup_delays(cls, *args):
        print('setup delay')
        cls._delayed_methods = []
        for owner, fn_name in args:
            original_fn = getattr(owner, fn_name)
            cls._delayed_methods.append((owner, fn_name, original_fn))
            setattr(owner, fn_name, delay(original_fn))

    @classmethod
    def _teardown_delays(cls):
        print('stop delay')
        for owner, fn_name, original in cls._delayed_methods:
            setattr(owner, fn_name, original)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_delays(
            (PickupDateJoinSerializer, 'update'),
            # (sql.InsertQuery, '__init__')
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._teardown_delays()
    """
    def test_single_user_joins_pickup_concurrently(self):
        data = Fixture(members=1)
        member = data.members[0]

        threads = []
        responses = []

        clients = []
        n_clients = 4
        for id in range(n_clients):
            client = CSRFSession(self.live_server_url)
            client.get('/api/auth/status/')
            r = client.post('/api/auth/', json={'email': member.email, 'password': member.display_name})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            clients.append(client)

        def do_requests(client):
            responses.append(client.post(data.join_url))

        [threads.append(threading.Thread(target=do_requests, kwargs={'client': c})) for c in clients]
        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        self.assertEqual(n_clients - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))
        data.pickup.refresh_from_db()
        self.assertEqual(data.pickup.collectors.count(), 1)
    """
    def test_many_users_join_pickup_concurrently(self):
        data = Fixture(members=2)

        threads = []
        responses = []

        clients = []
        n_clients = len(data.members)
        for member in data.members:
            client = CSRFSession(self.live_server_url)
            client.get('/api/auth/status/')
            r = client.post('/api/auth/', json={'email': member.email, 'password': member.display_name})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            clients.append(client)

        def do_requests(client):
            responses.append(client.post(data.join_url))

        [threads.append(threading.Thread(target=do_requests, kwargs={'client': c})) for c in clients]
        [t.start() for t in threads]
        [t.join() for t in threads]

        # self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        # self.assertEqual(n_clients - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))
        self.assertEqual(data.pickup.collectors.count(), 1)


"""
    def test_single_user_joins_pickup_concurrently(self):
        data = Fixture(members=1)
        member = data.members[0]

        mp = multiprocessing.get_context('fork')

        taskq = mp.Queue()
        responseq = mp.Queue()

        clients = []
        for id in range(4):
            client = CSRFSession(self.live_server_url)
            client.get('/api/auth/status/')
            r = client.post('/api/auth/', json={'email': member.email, 'password': member.display_name})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            clients.append(client)

        def leave_all():
            [c.post(data.remove_url) for c in clients]

        for id, client in enumerate(clients):
            mp.Process(
                target=do_requests_process,
                kwargs={
                    'iq': taskq,
                    'oq': responseq,
                    'host': self.live_server_url,
                    'url': data.join_url,
                    'cookies': client.cookies,
                    'headers': client.headers,
                }
            ).start()

        workload = 10
        for _ in range(4):
            leave_all()
            for id in range(workload):
                taskq.put('task{}'.format(id))

            responses = []
            for _ in range(workload):
                (task, r) = responseq.get()
                responses.append(r)

            self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
            self.assertEqual(workload - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))

        for _ in clients:
            taskq.put('STOP')

        [c.close() for c in clients]
"""


