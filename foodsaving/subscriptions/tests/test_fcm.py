from contextlib import contextmanager
from importlib import reload
from unittest.mock import patch

import requests_mock
from django.test import TestCase

import foodsaving.subscriptions.fcm
from foodsaving.subscriptions import fcm
from foodsaving.subscriptions.factories import PushSubscriptionFactory
from foodsaving.subscriptions.fcm import _notify_multiple_devices
from foodsaving.subscriptions.models import PushSubscription


@contextmanager
def logger_warning_mock():
    with patch('logging.Logger.warning') as mock_logging:
        yield mock_logging


@contextmanager
def override_fcm_key(key=None):
    from django.conf import settings

    # make sure to back up original key if present
    original = None
    if hasattr(settings, 'FCM_SERVER_KEY'):
        original = settings.FCM_SERVER_KEY

    if not key:
        # remove original key if it exists
        if hasattr(settings, 'FCM_SERVER_KEY'):
            del settings.FCM_SERVER_KEY
    else:
        # or override original key
        settings.FCM_SERVER_KEY = key
    reload(foodsaving.subscriptions.fcm)
    yield

    if hasattr(settings, 'FCM_SERVER_KEY'):
        del settings.FCM_SERVER_KEY

    # restore original key
    if original:
        settings.FCM_SERVER_KEY = original
    reload(foodsaving.subscriptions.fcm)


@requests_mock.Mocker()
class FCMTests(TestCase):
    def test_sends_without_error(self, m):
        m.post('https://fcm.googleapis.com/fcm/send', json={})
        _notify_multiple_devices(registration_ids=['mytoken'])

    def test_removes_invalid_subscriptions(self, m):
        with override_fcm_key('something'):
            valid = PushSubscriptionFactory()
            invalid = PushSubscriptionFactory()
            invalid2 = PushSubscriptionFactory()
            m.post(
                'https://fcm.googleapis.com/fcm/send',
                json={
                    'results': [
                        {
                            # not an error
                        },
                        {
                            'error': 'InvalidRegistration'
                        },
                        {
                            'error': 'NotRegistered'
                        }
                    ]
                }
            )

            fcm.notify_subscribers([valid, invalid, invalid2], fcm_options={})
            self.assertEqual(PushSubscription.objects.filter(token=valid.token).count(), 1)
            self.assertEqual(PushSubscription.objects.filter(token=invalid.token).count(), 0)
            self.assertEqual(PushSubscription.objects.filter(token=invalid2.token).count(), 0)

    def test_continues_if_config_not_present(self, m):
        with logger_warning_mock() as warning_mock:
            with override_fcm_key():
                warning_mock.assert_called_with(
                    'Please configure FCM_SERVER_KEY in your settings to use push messaging'
                )
                result = _notify_multiple_devices(registration_ids=['mytoken'])
                self.assertEqual(result, (0, 0))


class FCMNotifySubscribersTests(TestCase):
    @patch('foodsaving.subscriptions.stats.write_points')
    @patch('foodsaving.subscriptions.fcm._notify_multiple_devices')
    def test_notify_subscribers(self, _notify_multiple_devices, write_points):
        web_subscriptions = [PushSubscriptionFactory(platform='web') for _ in range(3)]
        android_subscriptions = [PushSubscriptionFactory(platform='android') for _ in range(5)]
        subscriptions = web_subscriptions + android_subscriptions

        write_points.reset_mock()
        _notify_multiple_devices.return_value = ([1, 2, 3, 4, 5, 6], [0, 7])

        fcm.notify_subscribers(
            subscriptions,
            fcm_options={
                'message_title': 'heya',
            },
        )

        _notify_multiple_devices.assert_called_with(
            registration_ids=[item.token for item in subscriptions],
            message_title='heya',
        )

        write_points.assert_called_with([
            {
                'measurement': 'karrot.events',
                'tags': {
                    'platform': 'android',
                },
                'fields': {
                    'subscription_push': len(android_subscriptions) - 1,
                    'subscription_push_error': 1,
                },
            },
            {
                'measurement': 'karrot.events',
                'tags': {
                    'platform': 'web',
                },
                'fields': {
                    'subscription_push': len(web_subscriptions) - 1,
                    'subscription_push_error': 1
                },
            },
        ])
