import asyncio
import json
import pytest
from base64 import b64encode
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework.authtoken.models import Token

from foodsaving.subscriptions.consumers import SyncWebsocketConsumer, TokenAuthMiddleware, get_auth_token_from_headers
from foodsaving.subscriptions.models import ChannelSubscription
from foodsaving.users.factories import AsyncUserFactory


@pytest.fixture
async def communicator():
    communicator = WebsocketCommunicator(SyncWebsocketConsumer, '/')
    yield communicator
    await communicator.disconnect()


author_communicator = communicator

@pytest.mark.asyncio
@pytest.mark.django_db
class TestConsumer:
    async def test_adds_subscription(self, communicator):  # noqa: F811
        user = await AsyncUserFactory()
        communicator.scope['user'] = user
        assert ChannelSubscription.objects.filter(user=user).count() == 0
        await communicator.connect()
        assert ChannelSubscription.objects.filter(user=user).count() == 1, 'Did not add subscription'

    async def test_accepts_anonymous_connections(self, communicator):  # noqa: F811
        qs = ChannelSubscription.objects
        original_count = qs.count()
        await communicator.connect()
        assert qs.count() == original_count

    async def test_saves_reply_channel(self, communicator):  # noqa: F811
        user = await AsyncUserFactory()
        communicator.scope['user'] = user
        await communicator.connect()
        subscription = ChannelSubscription.objects.filter(user=user).first()
        assert subscription.reply_channel is not None
        await get_channel_layer().send(
            subscription.reply_channel, {
                'type': 'message.send',
                'text': json.dumps({
                    'message': 'hey! whaatsup?',
                }),
            }
        )
        response = await communicator.receive_json_from()
        assert response == {'message': 'hey! whaatsup?'}

    async def test_updates_lastseen(self, communicator):  # noqa: F811
        user = await AsyncUserFactory()
        communicator.scope['user'] = user
        await communicator.connect()

        # update the lastseen timestamp to ages ago
        the_past = timezone.now() - relativedelta(hours=6)
        await database_sync_to_async(ChannelSubscription.objects.filter(user=user).update)(lastseen_at=the_past)

        await communicator.send_json_to({'message': 'hey'})
        await asyncio.sleep(0.1)

        subscription = ChannelSubscription.objects.filter(user=user).first()
        difference = subscription.lastseen_at - the_past
        assert difference.seconds > 1000

    async def test_updates_away(self, communicator):  # noqa: F811
        user = await AsyncUserFactory()
        communicator.scope['user'] = user
        await communicator.connect()

        await communicator.send_json_to({'type': 'away'})
        await asyncio.sleep(0.1)
        subscription = ChannelSubscription.objects.get(user=user)
        assert subscription.away_at is not None

        await communicator.send_json_to({'type': 'back'})
        await asyncio.sleep(0.1)
        subscription.refresh_from_db()
        assert subscription.away_at is None

    async def test_removes_subscription(self, communicator):  # noqa: F811
        user = await AsyncUserFactory()
        communicator.scope['user'] = user
        await communicator.connect()
        assert ChannelSubscription.objects.filter(user=user).count() == 1, 'Did not add subscription'

        await communicator.disconnect()
        assert ChannelSubscription.objects.filter(user=user).count() == 0, 'Did not remove subscription'


@pytest.fixture
async def user():
    yield await AsyncUserFactory()


@pytest.fixture
async def token_communicator(user):  # noqa: F811
    token = Token.objects.create(user=user)
    encoded = b64encode(token.key.encode('ascii')).decode('ascii')
    token_communicator = WebsocketCommunicator(
        TokenAuthMiddleware(SyncWebsocketConsumer),
        '/',
        headers=[[
            b'sec-websocket-protocol',
            'karrot.token,karrot.token.value.{}'.format(encoded.rstrip('=')).encode('ascii'),
        ]],
    )
    yield token_communicator
    await token_communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
class TestTokenAuth:
    async def test_user_is_added_to_scope(self, token_communicator, user):  # noqa: F811
        await token_communicator.connect()
        assert token_communicator.scope['user'] == user


class TestTokenUtil:
    def test_get_auth_token_from_headers(self):
        token = get_auth_token_from_headers([[
            b'sec-websocket-protocol',
            b'karrot.token,karrot.token.value.Zm9v',
        ]])
        assert token == 'foo'

    def test_get_auth_token_from_headers_with_removed_base64_padding(self):
        token = get_auth_token_from_headers([[
            b'sec-websocket-protocol',
            b'karrot.token,karrot.token.value.Zm9vMQ',
        ]])
        assert token == 'foo1'
