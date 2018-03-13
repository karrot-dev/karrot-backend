import asyncio
import json
from base64 import b64encode

import asynctest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from foodsaving.subscriptions.consumers import WebsocketConsumer, \
    get_auth_token_from_headers
from foodsaving.subscriptions.models import ChannelSubscription
from foodsaving.subscriptions.routing import TokenAuthMiddleware
from foodsaving.users.factories import UserFactory


class ConsumerTests(asynctest.TestCase):
    use_default_loop = True

    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_adds_subscription(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 0)
        await self.communicator.connect()
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 1, 'Did not add subscription')

    async def test_accepts_anonymous_connections(self):
        qs = ChannelSubscription.objects
        original_count = qs.count()
        await self.communicator.connect()
        self.assertEqual(qs.count(), original_count)

    async def test_saves_reply_channel(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        await self.communicator.connect()
        subscription = ChannelSubscription.objects.filter(user=user).first()
        self.assertIsNotNone(subscription.reply_channel)

        # send a message on it
        await get_channel_layer().send(
            subscription.reply_channel,
            {
                'type': 'message.send',
                'text': json.dumps({
                    'message': 'hey! whaatsup?',
                }),
            },
        )
        response = await self.communicator.receive_json_from()
        self.assertEqual(response, {'message': 'hey! whaatsup?'})

    async def test_updates_lastseen(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        await self.communicator.connect()

        # update the lastseen timestamp to ages ago
        the_past = timezone.now() - relativedelta(hours=6)
        ChannelSubscription.objects.filter(user=user).update(lastseen_at=the_past)

        await self.communicator.send_json_to({'message': 'hey'})
        await asyncio.sleep(0.1)

        subscription = ChannelSubscription.objects.filter(user=user).first()
        difference = subscription.lastseen_at - the_past
        self.assertGreater(difference.seconds, 1000)

    async def test_updates_away(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        await self.communicator.connect()

        await self.communicator.send_json_to({'type': 'away'})
        await asyncio.sleep(0.1)
        subscription = ChannelSubscription.objects.get(user=user)
        self.assertIsNotNone(subscription.away_at)

        await self.communicator.send_json_to({'type': 'back'})
        await asyncio.sleep(0.1)
        subscription.refresh_from_db()
        self.assertIsNone(subscription.away_at)

    async def test_removes_subscription(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        await self.communicator.connect()
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 1, 'Did not add subscription')

        # client.send_and_consume('websocket.disconnect', path='/')
        await self.communicator.disconnect()
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 0, 'Did not remove subscription')


class TokenAuthTests(asynctest.TestCase):
    use_default_loop = True

    def setUp(self):
        self.user = UserFactory()
        self.token = Token.objects.create(user=self.user)
        encoded = b64encode(self.token.key.encode('ascii')).decode('ascii')
        self.communicator = WebsocketCommunicator(
            TokenAuthMiddleware(WebsocketConsumer),
            '/',
            headers=[[
                b'sec-websocket-protocol',
                'karrot.token,karrot.token.value.{}'.format(encoded.rstrip('=')).encode('ascii')
            ]]
        )

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_foo(self):
        await self.communicator.connect()
        self.assertEqual(self.communicator.scope['user'], self.user)


class TokenUtilTests(TestCase):
    def test_get_auth_token_from_headers(self):
        token = get_auth_token_from_headers([
            [b'sec-websocket-protocol', b'karrot.token,karrot.token.value.Zm9v']
        ])
        self.assertEqual(token, 'foo')

    def test_get_auth_token_from_headers_with_removed_base64_padding(self):
        token = get_auth_token_from_headers([
            [b'sec-websocket-protocol', b'karrot.token,karrot.token.value.Zm9vMQ']
        ])
        self.assertEqual(token, 'foo1')
