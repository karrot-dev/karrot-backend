from dateutil.parser import parse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory

notification_url = '/api/notifications/'


class TestNotificationsAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_list_with_meta(self):
        # any notification
        Notification.objects.create(user=self.member, type=NotificationType.USER_BECAME_EDITOR)

        self.client.force_login(self.member)
        response = self.get_results(notification_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['notifications']), 1)
        self.assertEqual(response.data['meta'], {
            'marked_at': None,
        })

    def test_list_with_already_marked(self):
        # any notification
        Notification.objects.create(user=self.member, type=NotificationType.USER_BECAME_EDITOR)

        self.client.force_login(self.member)

        now = timezone.now()
        self.client.post(notification_url + 'mark_seen/')

        response = self.get_results(notification_url)
        self.assertGreaterEqual(parse(response.data['meta']['marked_at']), now)

    def test_mark_seen(self):
        self.client.force_login(self.member)

        response = self.client.post(notification_url + 'mark_seen/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        time1 = parse(response.data['marked_at'])
        self.assertLess(time1, timezone.now())

        # time should naturally increase each time we mark
        response = self.client.post(notification_url + 'mark_seen/')
        time2 = parse(response.data['marked_at'])
        self.assertLess(time1, time2)

    def test_mark_clicked(self):
        # any notification
        notification = Notification.objects.create(user=self.member, type=NotificationType.USER_BECAME_EDITOR)

        self.client.force_login(self.member)
        response = self.get_results(notification_url)
        self.assertFalse(response.data['notifications'][0]['clicked'])

        response = self.client.post(notification_url + str(notification.id) + '/mark_clicked/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['clicked'])
