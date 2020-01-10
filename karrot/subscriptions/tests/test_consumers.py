import asyncio
import json
from base64 import b64encode

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework.authtoken.models import Token

from karrot.subscriptions.consumers import WebsocketConsumer, TokenAuthMiddleware, get_auth_token_from_subprotocols
from karrot.subscriptions.models import ChannelSubscription
from karrot.subscriptions.routing import AllowedHostsAndFileOriginValidator
from karrot.users.factories import UserFactory

AsyncUserFactory = database_sync_to_async(UserFactory)


class Communicator():
    async def __aenter__(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        return self.communicator

    async def __aexit__(self, exc_type, exc, tb):
        await self.communicator.disconnect()


class TokenCommunicator():
    async def __aenter__(self):
        user = await AsyncUserFactory()
        token = await database_sync_to_async(Token.objects.create)(user=user)
        encoded = b64encode(token.key.encode('ascii')).decode('ascii')
        self.communicator = WebsocketCommunicator(
            TokenAuthMiddleware(WebsocketConsumer),
            '/',
            subprotocols=['karrot.token', 'karrot.token.value.{}'.format(encoded.rstrip('='))],
        )
        return self.communicator, user

    async def __aexit__(self, exc_type, exc, tb):
        await self.communicator.disconnect()


@database_sync_to_async
def get_subscription_count(**kwargs):
    return ChannelSubscription.objects.filter(**kwargs).count()


@database_sync_to_async
def get_subscription(**kwargs):
    return list(ChannelSubscription.objects.filter(**kwargs))


@pytest.mark.asyncio
@pytest.mark.django_db
class TestConsumer:
    async def test_adds_subscription(self):  # noqa: F811
        async with Communicator() as communicator:
            user = await AsyncUserFactory()
            communicator.scope['user'] = user
            assert (await get_subscription_count(user=user)) == 0
            await communicator.connect()
            assert (await get_subscription_count(user=user)) == 1, 'Did not add subscription'

    async def test_accepts_anonymous_connections(self):
        async with Communicator() as communicator:
            original_count = await get_subscription_count()
            await communicator.connect()
            assert (await get_subscription_count()) == original_count

    async def test_saves_reply_channel(self):
        async with Communicator() as communicator:
            user = await AsyncUserFactory()
            communicator.scope['user'] = user
            await communicator.connect()
            subscription = (await get_subscription(user=user))[0]
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

    async def test_updates_lastseen(self):
        async with Communicator() as communicator:
            user = await AsyncUserFactory()
            communicator.scope['user'] = user
            await communicator.connect()

            # update the lastseen timestamp to ages ago
            the_past = timezone.now() - relativedelta(hours=6)
            await database_sync_to_async(ChannelSubscription.objects.filter(user=user).update)(lastseen_at=the_past)

            await communicator.send_json_to({'message': 'hey'})
            await asyncio.sleep(0.1)

            subscription = (await get_subscription(user=user))[0]
            difference = subscription.lastseen_at - the_past
            assert difference.total_seconds() > 1000

    async def test_updates_away(self):
        async with Communicator() as communicator:
            user = await AsyncUserFactory()
            communicator.scope['user'] = user
            await communicator.connect()

            await communicator.send_json_to({'type': 'away'})
            await asyncio.sleep(0.1)
            subscription = (await get_subscription(user=user))[0]
            assert subscription.away_at is not None

            await communicator.send_json_to({'type': 'back'})
            await asyncio.sleep(0.1)
            await database_sync_to_async(subscription.refresh_from_db)()
            assert subscription.away_at is None

    async def test_removes_subscription(self):
        async with Communicator() as communicator:
            user = await AsyncUserFactory()
            communicator.scope['user'] = user
            await communicator.connect()
            assert (await get_subscription_count(user=user)) == 1, 'Did not add subscription'

            await communicator.disconnect()
            assert (await get_subscription_count(user=user)) == 0, 'Did not remove subscription'


@pytest.mark.asyncio
@pytest.mark.django_db
class TestTokenAuth:
    async def test_user_is_added_to_scope(self):
        async with TokenCommunicator() as (communicator, user):
            connected, subprotocol = await communicator.connect()
            assert connected
            assert (await get_subscription_count(user=user)) == 1, 'Did not login'


@pytest.mark.asyncio
@pytest.mark.django_db
class TestAllowedOriginValidator:
    async def test_can_connect_with_file_origin(self):
        application = AllowedHostsAndFileOriginValidator(WebsocketConsumer)
        communicator = WebsocketCommunicator(application, '/', headers=[(b'origin', b'file:///')])
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()


class TestTokenUtil:
    def test_get_auth_token_from_subprotocols(self):
        token = get_auth_token_from_subprotocols([
            'karrot.token',
            'karrot.token.value.Zm9v',
        ])
        assert token == 'foo'

    def test_get_auth_token_from_headers_with_removed_base64_padding(self):
        token = get_auth_token_from_subprotocols([
            'karrot.token',
            'karrot.token.value.Zm9vMQ',
        ])
        assert token == 'foo1'
