from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from karrot.applications import stats
from karrot.groups.factories import GroupFactory
from karrot.applications.factories import ApplicationFactory
from karrot.users.factories import UserFactory


class TestApplicationStats(TestCase):
    def test_application_stats(self):
        group = GroupFactory()

        [ApplicationFactory(group=group, user=UserFactory(), status='pending') for _ in range(3)]
        [ApplicationFactory(group=group, user=UserFactory(), status='accepted') for _ in range(4)]
        [ApplicationFactory(group=group, user=UserFactory(), status='declined') for _ in range(5)]
        [ApplicationFactory(group=group, user=UserFactory(), status='withdrawn') for _ in range(6)]

        points = stats.get_application_stats(group)

        self.assertEqual(
            points, [{
                'measurement': 'karrot.group.applications',
                'tags': {
                    'group': str(group.id),
                    'group_status': 'active',
                },
                'fields': {
                    'count_total': 18,
                    'count_status_pending': 3,
                    'count_status_accepted': 4,
                    'count_status_declined': 5,
                    'count_status_withdrawn': 6,
                },
            }]
        )

    @patch('karrot.applications.stats.write_points')
    def test_application_status_update(self, write_points):
        write_points.reset_mock()

        two_hours_ago = timezone.now() - relativedelta(hours=2)

        application = ApplicationFactory(group=GroupFactory(), user=UserFactory(), created_at=two_hours_ago)

        write_points.assert_called_with([{
            'measurement': 'karrot.events',
            'tags': {
                'group': str(application.group.id),
                'group_status': application.group.status,
            },
            'fields': {
                'application_pending': 1,
            },
        }])

        write_points.reset_mock()
        application.status = 'accepted'
        application.save()

        write_points.assert_called_with([{
            'measurement': 'karrot.events',
            'tags': {
                'group': str(application.group.id),
                'group_status': application.group.status,
                'application_status': application.status,
            },
            'fields': {
                'application_accepted': 1,
                'application_alive_seconds': 60 * 60 * 2,
                'application_accepted_alive_seconds': 60 * 60 * 2,
            },
        }])
