import json
from typing import TypedDict

import sentry_sdk
from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.serializers.json import DjangoJSONEncoder
from typing_extensions import NotRequired

from karrot.subscriptions import stats

channel_layer = get_channel_layer()
channel_layer_send_sync = async_to_sync(channel_layer.send)


class PushNotifyOptions(TypedDict):
    title: str
    body: NotRequired[str]
    tag: NotRequired[str]
    url: NotRequired[str]
    image_url: NotRequired[str]


def send_in_channel(channel, topic, payload):
    message = {
        "type": "message.send",
        "text": json.dumps(
            {
                "topic": topic,
                "payload": payload,
            },
            cls=DjangoJSONEncoder,
        ),
    }
    try:
        channel_layer_send_sync(channel, message)
    except ChannelFull:
        # TODO investigate this more
        # maybe this means the subscription is invalid now?
        sentry_sdk.capture_exception()
    except RuntimeError:
        # TODO investigate this more (but let the code continue in the meantime...)
        sentry_sdk.capture_exception()
    else:
        stats.pushed_via_websocket(topic)


class MockRequest:
    def __init__(self, user=None, META=None):
        self.user = user or AnonymousUser()
        self.headers = {}
        self.META = META or {}

    @staticmethod
    def build_absolute_uri(path):
        return settings.HOSTNAME + path
