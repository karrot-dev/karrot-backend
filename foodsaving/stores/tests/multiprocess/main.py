import multiprocessing
import unittest

import requests
from rest_framework import status

"""
Run server with manage.py runserver
Generate some sample data with manage.py create_sample_data

Find 4 users in the same group and a pickup date they can access. Fill out next lines and run test:
python main.py
"""

credentials = [
    {'email': '357462christopher64@roberson.biz', 'password': '123'},
    {'email': '199627pdawson@yahoo.com', 'password': '123'},
    {'email': '576808scott33@glover.com', 'password': '123'},
    {'email': '87002moorecharles@yahoo.com', 'password': '123'}
]
pickup_url = 'http://localhost:8000/api/pickup-dates/127/'


def do_requests_process(iq, oq, cookies=None, headers=None, pickup_url=None):
    client = CSRFSession()
    client.cookies = cookies
    client.headers.update(headers)

    for task in iter(iq.get, 'STOP'):
        response = client.post(pickup_url + 'add/')
        oq.put((task, response))

    client.close()


class CSRFSession(requests.Session):
    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        csrftoken = self.cookies['csrftoken']
        self.headers.update({'X-CSRFToken': csrftoken})
        return response


class TestPickupDatesAPIConcurrently(unittest.TestCase):
    def test_join_pickup_as_member(self):
        mp = multiprocessing.get_context('fork')

        taskq = mp.Queue(30)
        responseq = mp.Queue(30)

        clients = []
        for id in range(4):
            client = CSRFSession()
            client.get('http://localhost:8000/api/auth/status/')
            r = client.post('http://localhost:8000/api/auth/', json=credentials[id])
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            clients.append(client)

        def leave_all():
            [c.post(pickup_url + 'remove/') for c in clients]

        for id, client in enumerate(clients):
            mp.Process(
                target=do_requests_process,
                kwargs={
                    'iq': taskq,
                    'oq': responseq,
                    'cookies': client.cookies,
                    'headers': client.headers,
                    'pickup_url': pickup_url
                }
            ).start()

        workload = 10
        for _ in range(10):
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


if __name__ == '__main__':
    unittest.main()
