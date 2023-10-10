from typing import List

from django.conf import settings
from orjson import orjson
from pywebpush import webpush, WebPushException

from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.stats import pushed_via_web_push
from karrot.subscriptions.utils import PushNotifyOptions


def notify_subscribers(*, subscriptions: List[WebPushSubscription], fcm_options: PushNotifyOptions):
    success_count = 0
    error_count = 0
    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": subscription.keys,
        }

        vapid_data = {
            'vapid_private_key': settings.VAPID_PRIVATE_KEY,
            'vapid_claims': {
                "sub": "mailto:{}".format(settings.VAPID_ADMIN_EMAIL)
            }
        }

        payload = {
            "title": fcm_options['message_title'],
        }

        if 'body' in fcm_options:
            payload['body'] = fcm_options['message_body'],

        if 'click_action' in fcm_options:
            payload['url'] = fcm_options['click_action']

        if 'tag' in fcm_options:
            payload['tag'] = fcm_options['tag']

        if 'image_url' in fcm_options:
            payload['image_url'] = fcm_options['image_url']

        try:
            webpush(
                subscription_info,
                orjson.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            )
            success_count += 1
        except WebPushException as ex:
            error_count += 1
            if ex.response is not None and ex.response.status_code == 410:
                # cannot just check if "ex.response" as it evaluates to false if present
                # and status < 400
                subscription.delete()
            else:
                raise ex

    pushed_via_web_push(success_count, error_count)
