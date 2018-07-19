import asyncio
import json
import os
import pathlib
from channels.db import database_sync_to_async
from shutil import copyfile

import asynctest
import django
import requests_mock
from channels.testing import WebsocketCommunicator
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from pyfcm.baseapi import BaseAPI as FCMApi

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import ConversationMessage
from foodsaving.groups.factories import GroupFactory
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.factories import PickupDateFactory, PickupDateSeriesFactory, FeedbackFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.subscriptions.consumers import WebsocketConsumer
from foodsaving.subscriptions.models import PushSubscription, PushSubscriptionPlatform, ChannelSubscription
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


async def receive_responses_sorted_by_topic(communicator, count):
    responses = []
    for _ in range(count):
        responses.append(await communicator.receive_json_from(timeout=5))
    return sorted(responses, key=lambda r: r['topic'])


class ConversationReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        self.author_communicator = WebsocketCommunicator(WebsocketConsumer, '/')

    async def tearDown(self):
        await asyncio.wait([
            self.communicator.disconnect(),
            self.author_communicator.disconnect(),
        ])

    async def test_receives_messages(self):
        self.maxDiff = None
        communicator = self.communicator
        author_communicator = self.author_communicator

        user = await database_sync_to_async(UserFactory)()
        author = await database_sync_to_async(UserFactory)()

        # join a conversation
        conversation = await database_sync_to_async(ConversationFactory)()
        await database_sync_to_async(conversation.join)(user)
        await database_sync_to_async(conversation.join)(author)

        # login and connect

        communicator.scope['user'] = user
        await communicator.connect()

        author_communicator.scope['user'] = author
        await author_communicator.connect()

        # add a message to the conversation
        message = await database_sync_to_async(ConversationMessage.objects.create
                                               )(conversation=conversation, content='yay', author=author)

        responses = await receive_responses_sorted_by_topic(communicator, 2)

        # they should get an updated conversation object
        responses[0]['payload']['created_at'] = parse(responses[0]['payload']['created_at'])
        responses[0]['payload']['updated_at'] = parse(responses[0]['payload']['updated_at'])
        del responses[0]['payload']['participants']
        self.assertEqual(
            responses[0], {
                'topic': 'conversations:conversation',
                'payload': {
                    'id': conversation.id,
                    'created_at': conversation.created_at,
                    'updated_at': conversation.updated_at,
                    'seen_up_to': None,
                    'unread_message_count': 1,
                    'email_notifications': True,
                }
            }
        )

        # and the message
        responses[1]['payload']['created_at'] = parse(responses[1]['payload']['created_at'])
        self.assertEqual(
            responses[1], {
                'topic': 'conversations:message',
                'payload': {
                    'id': message.id,
                    'content': message.content,
                    'author': message.author.id,
                    'conversation': conversation.id,
                    'created_at': message.created_at,
                    'received_via': '',
                    'reactions': []
                }
            }
        )

        # author should get message & updated conversations object too

        author_responses = await receive_responses_sorted_by_topic(author_communicator, 2)

        # Author receives more recent `update_at` time,
        # because their `seen_up_to` status is set after sending the message.
        author_participant = conversation.conversationparticipant_set.get(user=author)
        author_responses[0]['payload']['created_at'] = parse(author_responses[0]['payload']['created_at'])
        author_responses[0]['payload']['updated_at'] = parse(author_responses[0]['payload']['updated_at'])
        del author_responses[0]['payload']['participants']
        self.assertEqual(
            author_responses[0], {
                'topic': 'conversations:conversation',
                'payload': {
                    'id': conversation.id,
                    'created_at': conversation.created_at,
                    'updated_at': author_participant.updated_at,
                    'seen_up_to': message.id,
                    'unread_message_count': 0,
                    'email_notifications': True,
                }
            }
        )

        author_responses[1]['payload']['created_at'] = parse(author_responses[1]['payload']['created_at'])
        self.assertEqual(
            author_responses[1], {
                'topic': 'conversations:message',
                'payload': {
                    'id': message.id,
                    'content': message.content,
                    'author': message.author.id,
                    'conversation': conversation.id,
                    'created_at': message.created_at,
                    'received_via': '',
                    'reactions': []
                }
            }
        )

    async def tests_receive_message_on_leave(self):
        communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        user = UserFactory()

        # join a conversation
        conversation = ConversationFactory()
        conversation.join(user)

        # login and connect
        communicator.scope['user'] = user
        await communicator.connect()

        conversation.leave(user)

        response = await communicator.receive_json_from()

        self.assertEqual(response, {'topic': 'conversations:leave', 'payload': {'id': conversation.id}})


class GroupReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_group_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        name = faker.name()
        self.group.name = name
        self.group.save()

        responses = await receive_responses_sorted_by_topic(self.communicator, 2)

        self.assertEqual(responses[0]['topic'], 'groups:group_detail')
        self.assertEqual(responses[0]['payload']['name'], name)
        self.assertTrue('description' in responses[0]['payload'])

        self.assertEqual(responses[1]['topic'], 'groups:group_preview')
        self.assertEqual(responses[1]['payload']['name'], name)
        self.assertTrue('description' not in responses[1]['payload'])

    async def test_receive_group_changes_as_nonmember(self):
        self.communicator.scope['user'] = self.user
        await self.communicator.connect()

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'groups:group_preview')
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])


class InvitationReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_invitation_updates(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'invitations:invitation')
        self.assertEqual(response['payload']['email'], invitation.email)

    async def test_receive_invitation_accept(self):
        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)
        user = UserFactory()

        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        id = invitation.id
        invitation.accept(user)

        responses = await receive_responses_sorted_by_topic(self.communicator, 3)

        self.assertEqual(responses[0]['topic'], 'history:history')

        self.assertEqual(responses[1]['topic'], 'invitations:invitation_accept')
        self.assertEqual(responses[1]['payload']['id'], id)

        self.assertEqual(responses[2]['topic'], 'users:user')
        self.assertEqual(responses[2]['payload']['id'], user.id)


class StoreReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_store_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        name = faker.name()
        self.store.name = name
        self.store.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'stores:store')
        self.assertEqual(response['payload']['name'], name)


class PickupDateReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_pickup_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        # change property
        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc)
        self.pickup.date = date
        self.pickup.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(parse(response['payload']['date']), date)

        # join
        self.pickup.collectors.add(self.member)

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(response['payload']['collector_ids'], [self.member.id])

        # leave
        self.pickup.collectors.remove(self.member)

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(response['payload']['collector_ids'], [])

    async def test_receive_pickup_delete(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        self.pickup.deleted = True
        self.pickup.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:pickupdate_deleted')
        self.assertEqual(response['payload']['id'], self.pickup.id)


class PickupDateSeriesReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)

        # Create far in the future to generate no pickup dates
        # They would lead to interfering websocket messages
        self.series = PickupDateSeriesFactory(store=self.store, start_date=timezone.now() + relativedelta(months=2))

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_series_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc) + relativedelta(months=2)
        self.series.start_date = date
        self.series.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:series')
        self.assertEqual(parse(response['payload']['start_date']), date)

    async def test_receive_series_delete(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        id = self.series.id
        self.series.delete()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'pickups:series_deleted')
        self.assertEqual(response['payload']['id'], id)


class FeedbackReceiverTests(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_feedback_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        feedback = FeedbackFactory(given_by=self.member, about=self.pickup)

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'feedback:feedback')
        self.assertEqual(response['payload']['weight'], feedback.weight)


class FinishedPickupReceiverTest(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')

        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store, collectors=[self.member])

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_feedback_possible_and_history(self):
        self.pickup.date = timezone.now() - relativedelta(days=1)
        self.pickup.save()

        self.communicator.scope['user'] = self.member
        await self.communicator.connect()
        call_command('process_finished_pickup_dates')

        responses = await receive_responses_sorted_by_topic(self.communicator, 2)

        self.assertEqual(responses[0]['topic'], 'history:history')
        self.assertEqual(responses[0]['payload']['typus'], 'PICKUP_DONE')

        self.assertEqual(responses[1]['topic'], 'pickups:feedback_possible')
        self.assertEqual(responses[1]['payload']['id'], self.pickup.id)


class UserReceiverTest(asynctest.TestCase):
    def setUp(self):
        self.communicator = WebsocketCommunicator(WebsocketConsumer, '/')
        self.member = UserFactory()
        self.other_member = UserFactory()
        self.unrelated_user = UserFactory()
        self.group = GroupFactory(members=[self.member, self.other_member])
        pathlib.Path(settings.MEDIA_ROOT).mkdir(exist_ok=True)
        copyfile(
            os.path.join(os.path.dirname(__file__), './photo.jpg'), os.path.join(settings.MEDIA_ROOT, 'photo.jpg')
        )
        self.member.photo = 'photo.jpg'
        self.member.save()
        self.other_member.photo = 'photo.jpg'
        self.other_member.save()

    async def tearDown(self):
        await self.communicator.disconnect()

    async def test_receive_own_user_changes(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        name = faker.name()
        self.member.display_name = name
        self.member.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'auth:user')
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

    async def test_receive_changes_of_other_user(self):
        self.communicator.scope['user'] = self.member
        await self.communicator.connect()

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        response = await self.communicator.receive_json_from()
        self.assertEqual(response['topic'], 'users:user')
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' not in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

    async def test_unrelated_user_receives_no_changes(self):
        self.communicator.scope['user'] = self.unrelated_user
        await self.communicator.connect()

        self.member.display_name = faker.name()
        self.member.save()


@requests_mock.Mocker()
class ReceiverPushTests(django.test.TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.author = UserFactory()

        self.token = faker.uuid4()
        self.content = faker.text()

        # join a conversation
        self.conversation = ConversationFactory()
        self.conversation.join(self.user)
        self.conversation.join(self.author)

        # add a push subscriber
        PushSubscription.objects.create(user=self.user, token=self.token, platform=PushSubscriptionPlatform.ANDROID)

    def test_sends_to_push_subscribers(self, m):
        def check_json_data(request):
            data = json.loads(request.body.decode('utf-8'))
            self.assertEqual(data['notification']['title'], self.author.display_name)
            self.assertEqual(data['notification']['body'], self.content)
            self.assertEqual(data['to'], self.token)
            return True

        m.post(FCMApi.FCM_END_POINT, json={}, additional_matcher=check_json_data)

        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)

    def test_does_not_send_push_notification_if_active_channel_subscription(self, m):
        # add a channel subscription to prevent the push being sent
        ChannelSubscription.objects.create(user=self.user, reply_channel='foo')
        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)
        # if it sent a push message, the requests mock would complain there is no matching request...

    def test_send_push_notification_if_channel_subscription_is_away(self, m):
        def check_json_data(request):
            data = json.loads(request.body.decode('utf-8'))
            self.assertEqual(data['notification']['title'], self.author.display_name)
            self.assertEqual(data['notification']['body'], self.content)
            self.assertEqual(data['to'], self.token)
            return True

        m.post(FCMApi.FCM_END_POINT, json={}, additional_matcher=check_json_data)

        # add a channel subscription to prevent the push being sent
        ChannelSubscription.objects.create(user=self.user, reply_channel='foo', away_at=timezone.now())

        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)


@requests_mock.Mocker()
class GroupConversationReceiverPushTests(django.test.TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.user = UserFactory()
        self.author = UserFactory()
        self.group.add_member(self.user)
        self.group.add_member(self.author)

        self.token = faker.uuid4()
        self.content = faker.text()

        self.conversation = self.group.conversation

        # add a push subscriber
        PushSubscription.objects.create(user=self.user, token=self.token, platform=PushSubscriptionPlatform.ANDROID)

    def test_sends_to_push_subscribers(self, m):
        def check_json_data(request):
            data = json.loads(request.body.decode('utf-8'))
            self.assertEqual(data['notification']['title'], self.group.name + ' / ' + self.author.display_name)
            self.assertEqual(data['notification']['body'], self.content)
            self.assertEqual(data['to'], self.token)
            return True

        m.post(FCMApi.FCM_END_POINT, json={}, additional_matcher=check_json_data)

        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)
