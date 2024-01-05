from random import shuffle
from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import TestCase
from factory.django import mute_signals
from pywebpush import WebPushException
from requests import Response

from karrot.subscriptions.factories import WebPushSubscriptionFactory
from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.web_push import notify_subscribers


def mock_webpush(subscription_info, *args, **kwargs):
    if subscription_info["keys"] == "INVALID":
        res = Response()
        res.status_code = 410
        raise WebPushException("invalid", res)


class WebPushTests(TestCase):
    def test_removes_invalid_subscriptions(self):
        valid = []
        invalid = []
        with mute_signals(post_save):
            for _ in range(4):
                valid.append(WebPushSubscriptionFactory())
                invalid.append(WebPushSubscriptionFactory(keys="INVALID"))

        with patch("karrot.subscriptions.web_push.webpush", side_effect=mock_webpush):
            subscriptions = [*valid, *invalid]
            shuffle(subscriptions)
            notify_subscribers(
                subscriptions=subscriptions,
                title="Hey",
            )

        self.assertEqual(WebPushSubscription.objects.filter(id__in=[entry.id for entry in valid]).count(), len(valid))
        self.assertEqual(WebPushSubscription.objects.filter(id__in=[entry.id for entry in invalid]).count(), 0)


class WebPushNotifySubscribersTests(TestCase):
    @patch("karrot.subscriptions.stats.write_points")
    def test_notify_subscribers(self, write_points):
        success_count = 7
        error_count = 4
        subscriptions = []
        with mute_signals(post_save):
            for _ in range(success_count):
                subscriptions.append(WebPushSubscriptionFactory())
            for _ in range(error_count):
                subscriptions.append(WebPushSubscriptionFactory(keys="INVALID"))

        with patch("karrot.subscriptions.web_push.webpush", side_effect=mock_webpush) as webpush:
            write_points.reset_mock()

            notify_subscribers(
                subscriptions=subscriptions,
                title="heya",
            )

            self.assertEqual(len(webpush.call_args_list), len(subscriptions))

            write_points.assert_called_with(
                [
                    {
                        "measurement": "karrot.events",
                        "tags": {
                            "platform": "web_push",
                        },
                        "fields": {
                            "subscription_push": success_count,
                            "subscription_push_error": error_count,
                        },
                    },
                ]
            )
