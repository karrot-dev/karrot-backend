import requests_mock
from django.test import TestCase

from foodsaving.subscriptions.fcm import notify_multiple_devices
from foodsaving.subscriptions.models import PushSubscription
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


@requests_mock.Mocker()
class FCMTests(TestCase):
    def test_sends_without_error(self, m):
        m.post('https://fcm.googleapis.com/fcm/send', json={})
        notify_multiple_devices(registration_ids=['mytoken'])

    def test_removes_invalid_subscriptions(self, m):
        m.post('https://fcm.googleapis.com/fcm/send', json={
            'results': [
                {
                    # not an error
                },
                {
                    'error': 'InvalidRegistration'
                }
            ]
        })
        user = UserFactory()
        valid_token = faker.uuid4()
        invalid_token = faker.uuid4()
        PushSubscription.objects.create(user=user, token=valid_token)
        PushSubscription.objects.create(user=user, token=invalid_token)
        notify_multiple_devices(registration_ids=[valid_token, invalid_token])
        self.assertEqual(PushSubscription.objects.filter(token=valid_token).count(), 1)
        self.assertEqual(PushSubscription.objects.filter(token=invalid_token).count(), 0)
