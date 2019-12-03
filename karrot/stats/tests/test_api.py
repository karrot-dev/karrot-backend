import random
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from karrot.utils.tests.fake import faker


def generate_stats(n):
    return [{
        'ms': random.randint(1, 3000),
        'ms_resources': random.randint(1, 3000),
        'first_load': random.choice([True, False]),
        'logged_in': random.choice([True, False]),
        'mobile': random.choice([True, False]),
        'group': random.choice([random.randint(1, 100), None]),
        'route_name': faker.name(),
        'route_path': faker.name(),
        'route_params': {
            'group_id': 3,
        }
    } for n in range(n)]


@patch('karrot.stats.stats.write_points')
class TestStatsInfoAPI(APITestCase):
    def test_writing_a_point(self, write_points):
        self.maxDiff = None
        stat = {
            'ms': 1000,
            'ms_resources': 5000,
            'first_load': True,
            'logged_in': True,
            'mobile': False,
            'group': 1,
            'route_name': 'group',
            'route_path': '/group',
            'route_params': {
                'group_id': 5,
                'foo': 'bar',
            }
        }
        response = self.client.post('/api/stats/', data={'stats': [stat]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points,), kwargs = write_points.call_args
        self.assertEqual(points, [{
            'measurement': 'karrot.stats.frontend',
            'fields': {
                'ms': stat['ms'],
                'ms_resources': stat['ms_resources'],
            },
            'tags': {
                'first_load': True,
                'logged_in': True,
                'mobile': False,
                'group': 1,
                'route_name': 'group',
                'route_path': '/group',
                'route_params__group_id': 5,
                'route_params__foo': 'bar',
            }
        }])

    def test_writing_many_points(self, write_points):
        n = 50
        stats = generate_stats(n)
        response = self.client.post('/api/stats/', data={'stats': stats}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points,), kwargs = write_points.call_args
        self.assertEqual(len(points), n)

    def test_writing_too_many_points(self, write_points):
        n = 60
        stats = generate_stats(n)
        response = self.client.post('/api/stats/', data={'stats': stats}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
