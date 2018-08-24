import json
import os
import pathlib
import requests_mock
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django.utils.crypto import get_random_string
from pyfcm.baseapi import BaseAPI as FCMApi
from shutil import copyfile
from unittest.mock import patch

from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import ConversationMessage, \
    ConversationMessageReaction
from foodsaving.groups.factories import GroupFactory
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.factories import FeedbackFactory, PickupDateFactory, \
    PickupDateSeriesFactory
from foodsaving.pickups.models import PickupDate
from foodsaving.stores.factories import StoreFactory
from foodsaving.subscriptions.models import ChannelSubscription, \
    PushSubscription, PushSubscriptionPlatform
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


def parse_dates(data):
    payload = data['payload']
    for k in ('created_at', 'updated_at'):
        if payload.get(k):
            payload[k] = parse(payload[k])


def make_conversation_message_broadcast(message, **kwargs):
    response = {
        'topic': 'conversations:message',
        'payload': {
            'id': message.id,
            'content': message.content,
            'author': message.author.id,
            'conversation': message.conversation.id,
            'created_at': message.created_at,
            'updated_at': message.updated_at,
            'received_via': '',
            'reactions': [],
            'is_editable': False,
            'thread': None,
            'thread_meta': None,
        }
    }
    response['payload'].update(kwargs)
    return response


def make_conversation_broadcast(conversation, **kwargs):
    """ does not include participants"""
    response = {
        'topic': 'conversations:conversation',
        'payload': {
            'id': conversation.id,
            'updated_at': conversation.updated_at,
            'seen_up_to': None,
            'unread_message_count': 0,
            'email_notifications': True,
            'type': None,
            'target_id': None,
            'group': None,
        }
    }
    response['payload'].update(kwargs)
    return response


def generate_channel_name():
    return get_random_string()


class WSClient:
    def __init__(self, send_in_channel_mock):
        self.send_in_channel_mock = send_in_channel_mock
        self.reply_channel = None

    def connect_as(self, user):
        self.reply_channel = generate_channel_name()
        ChannelSubscription.objects.create(user=user, reply_channel=self.reply_channel)

    def call_args(self):
        def normalize_call_args(channel, topic, payload):
            return [channel, topic, payload]

        return [normalize_call_args(*args, **kwargs) for args, kwargs in self.send_in_channel_mock.call_args_list]

    @property
    def messages(self):
        return [{
            'topic': topic,
            'payload': payload,
        } for channel, topic, payload in self.call_args() if channel == self.reply_channel]


class WSTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.send_in_channel_patcher = patch('foodsaving.subscriptions.receivers.send_in_channel')
        self.send_in_channel_mock = self.send_in_channel_patcher.start()
        self.addCleanup(self.send_in_channel_patcher.stop)

    def connect_as(self, user):
        client = WSClient(self.send_in_channel_mock)
        client.connect_as(user)
        return client


class ConversationReceiverTests(WSTestCase):
    def test_receives_messages(self):
        self.maxDiff = None
        user = UserFactory()
        author = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[user, author])

        # login and connect
        client = self.connect_as(user)
        author_client = self.connect_as(author)

        # add a message to the conversation
        message = ConversationMessage.objects.create(conversation=conversation, content='yay', author=author)

        # hopefully they receive it!
        self.assertEqual(len(client.messages), 2, client.messages)
        response = client.messages[0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(message))

        # and they should get an updated conversation object
        response = client.messages[1]
        parse_dates(response)
        del response['payload']['participants']
        self.assertEqual(
            response,
            make_conversation_broadcast(
                conversation,
                unread_message_count=1,
                updated_at=response['payload']['updated_at'],  # TODO fix test
            )
        )

        # author should get message & updated conversations object too
        response = author_client.messages[0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(message, is_editable=True))

        # Author receives more recent `update_at` time,
        # because their `seen_up_to` status is set after sending the message.
        author_participant = conversation.conversationparticipant_set.get(user=author)
        response = author_client.messages[1]
        parse_dates(response)
        del response['payload']['participants']
        self.assertEqual(
            response,
            make_conversation_broadcast(conversation, seen_up_to=message.id, updated_at=author_participant.updated_at)
        )

    def tests_receive_message_on_leave(self):
        user = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[
            user,
        ])

        # login and connect
        client = self.connect_as(user)

        conversation.leave(user)

        self.assertEqual(client.messages[0], {'topic': 'conversations:leave', 'payload': {'id': conversation.id}})

    def test_other_participants_receive_update_on_join(self):
        user = UserFactory()
        joining_user = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[
            user,
        ])
        # login and connect
        client = self.connect_as(user)

        conversation.join(joining_user)

        response = client.messages[0]

        self.assertEqual(response['topic'], 'conversations:conversation')
        self.assertEqual(set(response['payload']['participants']), {user.id, joining_user.id})

    def test_other_participants_receive_update_on_leave(self):
        user = UserFactory()
        leaving_user = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[user, leaving_user])

        # login and connect
        client = self.connect_as(user)

        conversation.leave(leaving_user)

        response = client.messages[0]

        self.assertEqual(response['topic'], 'conversations:conversation')
        self.assertEqual(response['payload']['participants'], [user.id])


class ConversationThreadReceiverTests(WSTestCase):
    def test_receives_messages(self):
        self.maxDiff = None
        user = UserFactory()
        author = UserFactory()

        conversation = ConversationFactory(participants=[user, author])
        thread = conversation.messages.create(author=user, content='yay')

        # login and connect
        client = self.connect_as(user)
        author_client = self.connect_as(author)

        reply = ConversationMessage.objects.create(
            conversation=conversation,
            thread=thread,
            content='really yay?',
            author=author,
        )

        # user receive message
        response = client.messages[0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(
            reply,
            thread=thread.id,
        ))

        # and they should get an updated thread object
        response = client.messages[1]
        parse_dates(response)
        self.assertEqual(
            response,
            make_conversation_message_broadcast(
                thread,
                thread_meta={
                    'is_participant': True,
                    'muted': False,
                    'participants': [user.id, author.id],
                    'reply_count': 1,
                    'seen_up_to': None,
                    'unread_reply_count': 1
                },
                thread=thread.id,
                is_editable=True,  # user is author of thread message
                updated_at=response['payload']['updated_at'],  # TODO fix test
            )
        )

        # reply author should get message too
        response = author_client.messages[0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(reply, is_editable=True, thread=thread.id))

        # Author receives more recent `update_at` time,
        # because their `seen_up_to` status is set after sending the message.
        response = author_client.messages[1]
        parse_dates(response)
        self.assertEqual(
            response,
            make_conversation_message_broadcast(
                thread,
                thread=thread.id,
                thread_meta={
                    'is_participant': True,
                    'muted': False,
                    'participants': [user.id, author.id],
                    'reply_count': 1,
                    'seen_up_to': reply.id,
                    'unread_reply_count': 0,
                },
                updated_at=response['payload']['updated_at'],  # TODO fix test
            )
        )


class ConversationMessageReactionReceiverTests(WSTestCase):
    def test_receive_reaction_update(self):
        self.maxDiff = None
        author, user, reaction_user = [UserFactory() for _ in range(3)]
        conversation = ConversationFactory(participants=[author, user, reaction_user])
        message = ConversationMessage.objects.create(conversation=conversation, content='yay', author=author)

        # login and connect
        client = self.connect_as(user)

        # create reaction
        ConversationMessageReaction.objects.create(
            message=message,
            user=reaction_user,
            name='carrot',
        )

        # check if conversation update was received
        response = client.messages[0]
        parse_dates(response)
        self.assertEqual(
            response,
            make_conversation_message_broadcast(message, reactions=[{
                'name': 'carrot',
                'user': reaction_user.id
            }])
        )

    def test_receive_reaction_deletion(self):
        self.maxDiff = None
        author, user, reaction_user = [UserFactory() for _ in range(3)]
        conversation = ConversationFactory(participants=[author, user, reaction_user])
        message = ConversationMessage.objects.create(
            conversation=conversation,
            content='yay',
            author=author,
        )
        reaction = ConversationMessageReaction.objects.create(
            message=message,
            user=reaction_user,
            name='carrot',
        )

        # login and connect
        client = self.connect_as(user)

        reaction.delete()

        # check if conversation update was received
        response = client.messages[0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(message))


class GroupReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_receive_group_changes(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'groups:group_detail')
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' in response['payload'])

        response = self.client.messages[1]
        self.assertEqual(response['topic'], 'groups:group_preview')
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(self.client.messages), 2)

    def test_receive_group_changes_as_nonmember(self):
        self.client = self.connect_as(self.user)

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'groups:group_preview')
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(self.client.messages), 1)


class GroupApplicationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_member_receives_application_create(self):
        self.client = self.connect_as(self.member)

        application = GroupApplicationFactory(user=self.user, group=self.group)

        response = next(r for r in self.client.messages if r['topic'] == 'applications:update')
        self.assertEqual(response['payload']['id'], application.id)

        self.assertEqual(len(self.client.messages), 2)

    def test_member_receives_application_update(self):
        application = GroupApplicationFactory(user=self.user, group=self.group)

        self.client = self.connect_as(self.member)

        application.status = 'accepted'
        application.save()

        response = self.client.messages[0]
        self.assertEqual(response['payload']['id'], application.id)

        self.assertEqual(len(self.client.messages), 1)

    def test_applicant_receives_application_update(self):
        application = GroupApplicationFactory(user=self.user, group=self.group)

        self.client = self.connect_as(self.user)

        application.status = 'accepted'
        application.save()

        response = self.client.messages[0]
        self.assertEqual(response['payload']['id'], application.id)

        self.assertEqual(len(self.client.messages), 1)


class InvitationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_receive_invitation_updates(self):
        self.client = self.connect_as(self.member)

        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'invitations:invitation')
        self.assertEqual(response['payload']['email'], invitation.email)

        self.assertEqual(len(self.client.messages), 1)

    def test_receive_invitation_accept(self):
        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)
        user = UserFactory()

        self.client = self.connect_as(self.member)

        id = invitation.id
        invitation.accept(user)

        response = next(r for r in self.client.messages if r['topic'] == 'invitations:invitation_accept')
        self.assertEqual(response['payload']['id'], id)


class StoreReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)

    def test_receive_store_changes(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.store.name = name
        self.store.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'stores:store')
        self.assertEqual(response['payload']['name'], name)

        self.assertEqual(len(self.client.messages), 1)


class PickupDateReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

    def test_receive_pickup_changes(self):
        self.client = self.connect_as(self.member)

        # change property
        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc)
        self.pickup.date = date
        self.pickup.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(parse(response['payload']['date']), date)

        # join
        self.pickup.collectors.add(self.member)

        response = self.client.messages[1]
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(response['payload']['collector_ids'], [self.member.id])

        response = self.client.messages[2]
        self.assertEqual(response['topic'], 'conversations:conversation')
        self.assertEqual(response['payload']['participants'], [self.member.id])

        # leave
        self.pickup.collectors.remove(self.member)

        response = self.client.messages[3]
        self.assertEqual(response['topic'], 'pickups:pickupdate')
        self.assertEqual(response['payload']['collector_ids'], [])

        response = self.client.messages[4]
        self.assertEqual(response['topic'], 'conversations:leave')

        self.assertEqual(len(self.client.messages), 5)

    def test_receive_pickup_delete(self):
        self.client = self.connect_as(self.member)

        self.pickup.deleted = True
        self.pickup.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'pickups:pickupdate_deleted')
        self.assertEqual(response['payload']['id'], self.pickup.id)

        self.assertEqual(len(self.client.messages), 1)


class PickupDateSeriesReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)

        # Create far in the future to generate no pickup dates
        # They would lead to interfering websocket messages
        self.series = PickupDateSeriesFactory(store=self.store, start_date=timezone.now() + relativedelta(months=2))

    def test_receive_series_changes(self):
        self.client = self.connect_as(self.member)

        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc) + relativedelta(months=2)
        self.series.start_date = date
        self.series.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'pickups:series')
        self.assertEqual(parse(response['payload']['start_date']), date)

        self.assertEqual(len(self.client.messages), 1)

    def test_receive_series_delete(self):
        self.client = self.connect_as(self.member)

        id = self.series.id
        self.series.delete()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'pickups:series_deleted')
        self.assertEqual(response['payload']['id'], id)

        self.assertEqual(len(self.client.messages), 1)


class FeedbackReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store)

    def test_receive_feedback_changes(self):
        self.client = self.connect_as(self.member)

        feedback = FeedbackFactory(given_by=self.member, about=self.pickup)

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'feedback:feedback')
        self.assertEqual(response['payload']['weight'], feedback.weight)

        self.assertEqual(len(self.client.messages), 1)


class FinishedPickupReceiverTest(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store, collectors=[self.member])

    def test_receive_feedback_possible_and_history(self):
        self.pickup.date = timezone.now() - relativedelta(days=1)
        self.pickup.save()

        self.client = self.connect_as(self.member)
        PickupDate.objects.process_finished_pickup_dates()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'history:history')
        self.assertEqual(response['payload']['typus'], 'PICKUP_DONE')

        response = self.client.messages[1]
        self.assertEqual(response['topic'], 'pickups:feedback_possible')
        self.assertEqual(response['payload']['id'], self.pickup.id)

        self.assertEqual(len(self.client.messages), 2)


class UserReceiverTest(WSTestCase):
    def setUp(self):
        super().setUp()
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

    def test_receive_own_user_changes(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.member.display_name = name
        self.member.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'auth:user')
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

        self.assertEqual(len(self.client.messages), 1)

    def test_receive_changes_of_other_user(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'users:user')
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' not in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

        self.assertEqual(len(self.client.messages), 1)

    def test_do_not_send_too_many_updates(self):
        [GroupFactory(members=[self.member, self.other_member]) for _ in range(3)]

        self.client = self.connect_as(self.member)

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        self.assertEqual(len(self.client.messages), 1)
        response = self.client.messages[0]
        self.assertEqual(response['topic'], 'users:user')

    def test_unrelated_user_receives_no_changes(self):
        self.client = self.connect_as(self.unrelated_user)

        self.member.display_name = faker.name()
        self.member.save()

        self.assertEqual(len(self.client.messages), 0)


@requests_mock.Mocker()
class ReceiverPushTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.author = UserFactory()

        self.token = faker.uuid4()
        self.content = faker.text()

        # join a conversation
        self.conversation = ConversationFactory(participants=[self.user, self.author])

        # add a push subscriber
        PushSubscription.objects.create(
            user=self.user,
            token=self.token,
            platform=PushSubscriptionPlatform.ANDROID.value,
        )

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
class GroupConversationReceiverPushTests(TestCase):
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
        PushSubscription.objects.create(
            user=self.user,
            token=self.token,
            platform=PushSubscriptionPlatform.ANDROID.value,
        )

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
