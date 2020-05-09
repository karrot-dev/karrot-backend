import json

from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from raven.contrib.django.models import client as sentry_client

from karrot.subscriptions import stats

channel_layer = get_channel_layer()
channel_layer_send_sync = async_to_sync(channel_layer.send)


def send_in_channel(channel, topic, payload):
    message = {
        'type': 'message.send',
        'text': json.dumps({
            'topic': topic,
            'payload': payload,
        }),
    }
    try:
        channel_layer_send_sync(channel, message)
    except ChannelFull:
        # TODO investigate this more
        # maybe this means the subscription is invalid now?
        sentry_client.captureException()
    except RuntimeError:
        # TODO investigate this more (but let the code continue in the meantime...)
        sentry_client.captureException()
    else:
        stats.pushed_via_websocket(topic)


class MockRequest:
    def __init__(self, user=None):
        self.user = user or AnonymousUser()

    def build_absolute_uri(self, path):
        return settings.HOSTNAME + path
