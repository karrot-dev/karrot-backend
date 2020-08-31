import random
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range, Activity
from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.users.factories import VerifiedUserFactory
from karrot.utils.tests.fake import faker


def generate_stats(n):
    return [{
        'ms': random.randint(1, 3000),
        'ms_resources': random.randint(1, 3000),
        'first_load': random.choice([True, False]),
        'logged_in': random.choice([True, False]),
        'mobile': random.choice([True, False]),
        'app': random.choice([True, False]),
        'browser': faker.name(),
        'os': faker.name(),
        'dev': random.choice([True, False]),
        'group': random.choice([random.randint(1, 100), None]),
        'route_name': faker.name(),
        'route_path': faker.name(),
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
            'app': False,
            'browser': 'firefox',
            'os': 'linux',
            'dev': False,
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
        (points, ), kwargs = write_points.call_args
        self.assertEqual(
            points, [{
                'measurement': 'karrot.stats.frontend',
                'fields': {
                    'ms': stat['ms'],
                    'ms_resources': stat['ms_resources'],
                    'route_path': '/group',
                },
                'tags': {
                    'first_load': True,
                    'logged_in': True,
                    'mobile': False,
                    'app': False,
                    'browser': 'firefox',
                    'os': 'linux',
                    'dev': False,
                    'group': 1,
                    'route_name': 'group',
                }
            }]
        )

    def test_writing_many_points(self, write_points):
        n = 50
        stats = generate_stats(n)
        response = self.client.post('/api/stats/', data={'stats': stats}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points, ), kwargs = write_points.call_args
        self.assertEqual(len(points), n)

    def test_writing_too_many_points(self, write_points):
        n = 60
        stats = generate_stats(n)
        response = self.client.post('/api/stats/', data={'stats': stats}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class TestPlaceStatsInfoAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.place = PlaceFactory(group=self.group)

    def test_with_no_activity(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/stats/activity-history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0, response.data)
        # self.assertEqual([dict(entry) for entry in response.data], [self.expected_entry()], response.data)

    def setup_activity(self):
        self.date = to_range(timezone.now() + timedelta(days=33))
        self.just_before_the_activity_starts = self.date.start - timedelta(hours=1)
        self.after_the_activity_is_over = self.date.end + timedelta(hours=2)
        self.activity = ActivityFactory(place=self.place, date=self.date, max_participants=1)

    def test_join_and_leave_activity_missed(self):
        self.setup_activity()
        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f'/api/activities/{self.activity.id}/add/')

        with freeze_time(self.just_before_the_activity_starts, tick=True):

            # leave again, so soon! just before it's due to begin! naughty!
            self.client.post(f'/api/activities/{self.activity.id}/remove/')

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get('/api/stats/activity-history/', {'group': self.group.id, 'user': self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1)
            self.assertEqual([dict(entry) for entry in response.data],
                             [self.expected_entry({
                                 'leave_count': 1,
                                 'leave_late_count': 1,
                             })], response.data)

    def test_activity_done(self):
        self.setup_activity()
        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f'/api/activities/{self.activity.id}/add/')

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get('/api/stats/activity-history/', {'group': self.group.id, 'user': self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1, response.data)

    def test_join_and_leave_activity_done_by_other_user(self):
        self.setup_activity()
        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f'/api/activities/{self.activity.id}/add/')

        with freeze_time(self.just_before_the_activity_starts, tick=True):

            # leave again, so soon! just before it's due to begin! naughty!
            self.client.post(f'/api/activities/{self.activity.id}/remove/')

            # but phew! this time user 2 will do it instead...
            self.client.force_login(user=self.user2)
            self.client.post(f'/api/activities/{self.activity.id}/add/')

        self.client.force_login(user=self.user)

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get('/api/stats/activity-history/', {'group': self.group.id, 'user': self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            # nothing returned! our secret is safe...
            self.assertEqual(len(response.data), 0, response.data)

    def expected_entry(self, data=None):
        return {
            'place': self.place.id,
            'group': self.place.group.id,
            'done_count': 0,
            'leave_count': 0,
            'leave_late_count': 0,
            'feedback_weight': 0,
            **(data if data else {}),
        }
