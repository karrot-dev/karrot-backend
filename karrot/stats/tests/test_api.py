import random
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from karrot.utils.tests.fake import faker


def generate_stats(n):
    return [{
        'ms': random.randint(1, 3000),
        'first_load': random.choice([True, False]),
        'logged_in': random.choice([True, False]),
        'mobile': random.choice([True, False]),
        'route': faker.name(),
    } for n in range(n)]


@patch('karrot.stats.stats.write_points')
class TestStatsInfoAPI(APITestCase):
    def test_writing_a_point(self, write_points):
        stat = {
            'ms': 1000,
            'first_load': True,
            'logged_in': True,
            'mobile': False,
            'route': 'group',
        }
        response = self.client.post('/api/stats/', data={'stats': [stat]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points,), kwargs = write_points.call_args
        self.assertEqual(points, [{
            'measurement': 'karrot.stats.frontend',
            'fields': {
                'ms': stat['ms'],
            },
            'tags': {
                'first_load': True,
                'logged_in': True,
                'mobile': False,
                'route': 'group',
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
