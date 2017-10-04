import json
import multiprocessing
import unittest

import requests
from rest_framework import status

"""
Run server with manage.py runserver
Generate some sample data with manage.py create_sample_data

Find 4 users in the same group and a pickup date they can access. Fill out next lines and run test:
python foodsaving/stores/tests/process_concurrency/main.py
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

        n = 4
        for id in range(n):
            client = CSRFSession()
            client.get('http://localhost:8000/api/auth/status/')
            r = client.post('http://localhost:8000/api/auth/', json=credentials[id])
            self.assertEqual(r.status_code, status.HTTP_201_CREATED)

            client.post(pickup_url + 'remove/')

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

            client.close()

        workload = 16
        for id in range(workload):
            taskq.put('task{}'.format(id))

        responses = []
        for _ in range(workload):
            (task, r) = responseq.get()
            responses.append(r)

        for _ in range(n):
            taskq.put('STOP')

        for i in responses:
            if i.status_code not in (status.HTTP_200_OK, status.HTTP_403_FORBIDDEN):
                print(i, i.text)

        for i in responses:
            print(i.status_code)

        # self.assertEqual(1, sum(1 for r in responses if r.status_code == status.HTTP_200_OK))
        # self.assertEqual(workload - 1, sum(1 for r in responses if r.status_code == status.HTTP_403_FORBIDDEN))

        client = CSRFSession()
        client.get('http://localhost:8000/api/auth/status/')
        client.post('http://localhost:8000/api/auth/', json=credentials[0])
        r = client.get(pickup_url)
        print(json.loads(r.text))
        client.close()


if __name__ == '__main__':
    unittest.main()
