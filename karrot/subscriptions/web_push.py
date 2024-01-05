from typing import List

from cryptography.hazmat.primitives import serialization
from django.conf import settings
from orjson import orjson
from py_vapid import Vapid, b64urlencode
from pywebpush import WebPushException, webpush

from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.stats import pushed_via_web_push


def notify_subscribers(
    *,
    subscriptions: List[WebPushSubscription],
    title: str,
    body: str = "",
    tag: str = "",
    url: str = "",
    image_url: str = "",
):
    success_count = 0
    error_count = 0
    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": subscription.keys,
        }


        payload = {
            "title": title,
        }

        if body:
            payload["body"] = body

        if url:
            payload["url"] = url

        if tag:
            payload["tag"] = tag

        if image_url:
            payload["image_url"] = image_url

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


def generate_keypair():
    vapid = Vapid()
    vapid.generate_keys()
    return {
        "VAPID_PRIVATE_KEY": b64urlencode(
            vapid.private_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ),
        "VAPID_PUBLIC_KEY": b64urlencode(
            vapid.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
        ),
    }
