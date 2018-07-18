import asynctest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from foodsaving.subscriptions.consumers import WebsocketConsumer
from foodsaving.subscriptions.models import ChannelSubscription
from foodsaving.users.factories import UserFactory


class ConsumerTestsSync(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

    # def tearDown(self):
    #     async_to_sync(self.communicator.disconnect)()

    def test_adds_subscription(self):
        user = UserFactory()
        self.communicator.scope['user'] = user
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 0)
        async_to_sync(self.communicator.connect)()
        self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 1, 'Did not add subscription')


class ConsumerTests(asynctest.TestCase):
    #use_default_loop = True

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

    # async def test_saves_reply_channel(self):
    #
    #     user = UserFactory()
    #     self.communicator.scope['user'] = user
    #     await self.communicator.connect()
    #     subscription = ChannelSubscription.objects.filter(user=user).first()
    #     self.assertIsNotNone(subscription.reply_channel)
    #
    #     # send a message on it
    #     Channel(subscription.reply_channel).send({'message': 'hey! whaatsup?'})
    #     self.assertEqual(client.receive(json=True), {'message': 'hey! whaatsup?'})
    #
    # async def test_updates_lastseen(self):
    #
    #     user = UserFactory()
    #     self.communicator.scope['user'] = user
    #     await self.communicator.connect()
    #
    #     # update the lastseen timestamp to ages ago
    #     the_past = timezone.now() - relativedelta(hours=6)
    #     ChannelSubscription.objects.filter(user=user).update(lastseen_at=the_past)
    #
    #     # send a message, and it should update
    #     client.send_and_consume('websocket.receive', text={'message': 'hey'}, path='/')
    #     subscription = ChannelSubscription.objects.filter(user=user).first()
    #     difference = subscription.lastseen_at - the_past
    #     self.assertGreater(difference.seconds, 1000)
    #
    # async def test_updates_away(self):
    #
    #     user = UserFactory()
    #     self.communicator.scope['user'] = user
    #     await self.communicator.connect()
    #
    #     client.send_and_consume('websocket.receive', text={'type': 'away'}, path='/')
    #     subscription = ChannelSubscription.objects.get(user=user)
    #     self.assertIsNotNone(subscription.away_at)
    #
    #     client.send_and_consume('websocket.receive', text={'type': 'back'}, path='/')
    #     subscription.refresh_from_db()
    #     self.assertIsNone(subscription.away_at)
    #
    # async def test_removes_subscription(self):
    #
    #     user = UserFactory()
    #     self.communicator.scope['user'] = user
    #     await self.communicator.connect()
    #     self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 1, 'Did not add subscription')
    #
    #     client.send_and_consume('websocket.disconnect', path='/')
    #     self.assertEqual(ChannelSubscription.objects.filter(user=user).count(), 0, 'Did not remove subscription')


# class MockMessage(dict):
#     def __init__(self, *args, **kwargs):
#         self.update(*args, **kwargs)
#         self.session = {}
#         self.user = None
#
#     @property
#     def channel_session(self):
#         return self.session
#
#
# class TokenUtilTests(TestCase):
#     def test_check_for_auth_token_header(self):
#         message = MockMessage({
#             'headers': [
#                 [b'sec-websocket-protocol', b'karrot.token,karrot.token.value.Zm9v']
#             ]
#         })
#         check_for_auth_token_header(message)
#         self.assertEqual(message.channel_session['auth_token'], 'foo')
#
#     def test_check_for_auth_token_header_with_removed_base64_padding(self):
#         message = MockMessage({
#             'headers': [
#                 [b'sec-websocket-protocol', b'karrot.token,karrot.token.value.Zm9vMQ']
#             ]
#         })
#         check_for_auth_token_header(message)
#         self.assertEqual(message.channel_session['auth_token'], 'foo1')
#
#     def test_check_for_token_user(self):
#         user = UserFactory()
#         token = Token.objects.create(user=user)
#         message = MockMessage()
#         message.channel_session['auth_token'] = token.key
#         check_for_token_user(message)
#         self.assertEqual(message.user, user)
