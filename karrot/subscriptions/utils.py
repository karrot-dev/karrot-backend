import json

import sentry_sdk
from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.dispatch import receiver
from huey.contrib.djhuey import db_task

from karrot.subscriptions import stats
from karrot.utils.misc import on_transaction_commit

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
        sentry_sdk.capture_exception()
    except RuntimeError:
        # TODO investigate this more (but let the code continue in the meantime...)
        sentry_sdk.capture_exception()
    else:
        stats.pushed_via_websocket(topic)


class MockRequest:
    def __init__(self, user=None, META=None):
        self.user = user or AnonymousUser()
        self.META = META or {}

    def build_absolute_uri(self, path):
        return settings.HOSTNAME + path


def receiver_transaction_task(signal, **kwargs):
    """Register a signal handler that runs as huey db_task after transaction commit

    Useful for doing non-pressing work after write operations, e.g. sending websocket updates

    Can also be used outside of transactions, then it will run immediately (see docs for transaction.on_commit)
    """
    def inner(fn):
        receiver(signal, **kwargs)(on_transaction_commit(db_task()(fn)))

    return inner
