from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone

from karrot.groups.factories import GroupFactory
from karrot.notifications.models import Notification, NotificationType
from karrot.users.factories import UserFactory


class TestStats(TestCase):
    @patch('karrot.notifications.stats.write_points')
    def test_created(self, write_points):
        user = UserFactory()
        group = GroupFactory(members=[user])
        write_points.reset_mock()

        Notification.objects.create(
            user=user,
            type=NotificationType.USER_BECAME_EDITOR.value,
            context={'group': group.id},
        )

        write_points.assert_called_with([{
            'measurement': 'karrot.events',
            'tags': {
                'group': str(group.id),
                'group_status': group.status,
                'notification_type': NotificationType.USER_BECAME_EDITOR.value,
            },
            'fields': {
                'notification_created': 1,
            },
        }])

    @patch('karrot.notifications.stats.write_points')
    def test_clicked(self, write_points):
        user = UserFactory()
        group = GroupFactory(members=[user])
        two_hours_ago = timezone.now() - relativedelta(hours=2)
        notification = Notification.objects.create(
            created_at=two_hours_ago,
            user=user,
            type=NotificationType.USER_BECAME_EDITOR.value,
            context={'group': group.id},
        )
        write_points.reset_mock()

        notification.clicked = True
        notification.save()

        write_points.assert_called_with([{
            'measurement': 'karrot.events',
            'tags': {
                'group': str(group.id),
                'group_status': group.status,
                'notification_type': NotificationType.USER_BECAME_EDITOR.value,
            },
            'fields': {
                'notification_clicked': 1,
                'notification_clicked_seconds': 60 * 60 * 2,
            },
        }])
