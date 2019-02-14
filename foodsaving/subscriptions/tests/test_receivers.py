import itertools

import os
import pathlib
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django.utils.crypto import get_random_string
from operator import itemgetter
from shutil import copyfile
from unittest.mock import patch

from foodsaving.applications.factories import ApplicationFactory
from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import ConversationMessage, \
    ConversationMessageReaction, ConversationNotificationStatus
from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.invitations.models import Invitation
from foodsaving.issues.factories import IssueFactory
from foodsaving.pickups.factories import FeedbackFactory, PickupDateFactory, \
    PickupDateSeriesFactory
from foodsaving.pickups.models import PickupDate, to_range
from foodsaving.places.factories import PlaceFactory
from foodsaving.subscriptions.models import ChannelSubscription, \
    PushSubscription, PushSubscriptionPlatform
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.utils.tests.fake import faker


def parse_dates(data):
    payload = data['payload']
    for k in ('created_at', 'updated_at', 'edited_at'):
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
            'edited_at': message.edited_at,
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
            'notifications': ConversationNotificationStatus.ALL.value,
            'type': None,
            'target_id': None,
            'is_closed': False,
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

    @property
    def messages_by_topic(self):
        topic = itemgetter('topic')
        return {
            topic: list(group)
            for (topic, group) in itertools.groupby(sorted(self.messages, key=topic), key=topic)
        }


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

        response = self.client.messages_by_topic.get('groups:group_detail')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' in response['payload'])

        response = self.client.messages_by_topic.get('groups:group_preview')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(self.client.messages), 2)

    def test_receive_group_changes_as_nonmember(self):
        self.client = self.connect_as(self.user)

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = self.client.messages_by_topic.get('groups:group_preview')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(self.client.messages), 1)


class GroupMembershipReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_receive_group_join(self):
        member_client = self.connect_as(self.member)
        joining_client = self.connect_as(self.user)
        nonmember_client = self.connect_as(UserFactory())

        self.group.add_member(self.user)

        response = member_client.messages_by_topic.get('groups:group_detail')[0]
        self.assertIn(self.user.id, response['payload']['members'])
        self.assertIn(self.user.id, response['payload']['memberships'].keys())

        response = member_client.messages_by_topic.get('groups:group_preview')[0]
        self.assertIn(self.user.id, response['payload']['members'])
        self.assertNotIn('memberships', response['payload'])

        response = joining_client.messages_by_topic.get('groups:group_detail')[0]
        self.assertIn(self.user.id, response['payload']['members'])

        response = joining_client.messages_by_topic.get('groups:group_preview')[0]
        self.assertIn(self.user.id, response['payload']['members'])

        self.assertNotIn('groups:group_detail', nonmember_client.messages_by_topic.keys())
        response = nonmember_client.messages_by_topic.get('groups:group_preview')[0]
        self.assertIn(self.user.id, response['payload']['members'])
        self.assertNotIn('memberships', response['payload'])

    def test_receive_group_leave_as_leaving_user(self):
        client = self.connect_as(self.member)

        self.group.remove_member(self.member)

        response = client.messages_by_topic.get('groups:group_preview')[0]
        self.assertNotIn(self.user.id, response['payload']['members'])
        self.assertNotIn('memberships', response['payload'])
        self.assertEqual([m['topic'] for m in client.messages], [
            'history:history',
            'conversations:leave',
            'conversations:conversation',
            'groups:group_preview',
        ])

    def test_receive_group_roles_update(self):
        membership = self.group.add_member(self.user)
        client = self.connect_as(self.member)

        membership.add_roles([roles.GROUP_EDITOR])
        membership.save()

        response = client.messages_by_topic.get('groups:group_detail')[0]
        self.assertIn(roles.GROUP_EDITOR, response['payload']['memberships'][self.user.id]['roles'])

        self.assertEqual([m['topic'] for m in client.messages], [
            'notifications:notification',
            'groups:group_detail',
            'groups:group_preview',
        ])


class ApplicationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def application_update_messages(self):
        return [r for r in self.client.messages if r['topic'] == 'applications:update']

    def test_member_receives_application_create(self):
        self.client = self.connect_as(self.member)

        application = ApplicationFactory(user=self.user, group=self.group)

        messages = self.application_update_messages()
        self.assertEqual(len(messages), 1)
        response = messages[0]
        self.assertEqual(response['payload']['id'], application.id)

    def test_member_receives_application_update(self):
        application = ApplicationFactory(user=self.user, group=self.group)

        self.client = self.connect_as(self.member)

        application.status = 'accepted'
        application.save()

        messages = self.application_update_messages()
        self.assertEqual(len(messages), 1)
        response = messages[0]
        self.assertEqual(response['payload']['id'], application.id)

    def test_applicant_receives_application_update(self):
        application = ApplicationFactory(user=self.user, group=self.group)

        self.client = self.connect_as(self.user)

        application.status = 'accepted'
        application.save()

        messages = self.application_update_messages()
        self.assertEqual(len(messages), 1)
        response = messages[0]
        self.assertEqual(response['payload']['id'], application.id)


class InvitationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_receive_invitation_updates(self):
        self.client = self.connect_as(self.member)

        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)

        response = self.client.messages_by_topic.get('invitations:invitation')[0]
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


class PlaceReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)

    def test_receive_place_changes(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.place.name = name
        self.place.save()

        response = self.client.messages_by_topic.get('places:place')[0]
        self.assertEqual(response['payload']['name'], name)

        self.assertEqual(len(self.client.messages), 1)


class PickupDateReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place)

    def test_receive_pickup_changes(self):
        self.client = self.connect_as(self.member)

        # change property
        date = to_range(faker.future_datetime(end_date='+30d', tzinfo=timezone.utc))
        self.pickup.date = date
        self.pickup.save()

        response = self.client.messages_by_topic.get('pickups:pickupdate')[0]
        self.assertEqual(parse(response['payload']['date'][0]), date.start)

        # join
        self.client = self.connect_as(self.member)
        self.pickup.add_collector(self.member)

        response = self.client.messages_by_topic.get('pickups:pickupdate')[0]
        self.assertEqual(response['payload']['collectors'], [self.member.id])

        response = self.client.messages_by_topic.get('conversations:conversation')[0]
        self.assertEqual(response['payload']['participants'], [self.member.id])

        # leave
        self.client = self.connect_as(self.member)
        self.pickup.remove_collector(self.member)

        response = self.client.messages_by_topic.get('pickups:pickupdate')[0]
        self.assertEqual(response['payload']['collectors'], [])

        self.assertIn('conversations:leave', self.client.messages_by_topic.keys())

    def test_receive_pickup_delete(self):
        self.client = self.connect_as(self.member)

        pickup_id = self.pickup.id
        self.pickup.delete()

        response = self.client.messages_by_topic.get('pickups:pickupdate_deleted')[0]
        self.assertEqual(response['payload']['id'], pickup_id)

        self.assertEqual(len(self.client.messages), 1)


class PickupDateSeriesReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)

        # Create far in the future to generate no pickup dates
        # They would lead to interfering websocket messages
        self.series = PickupDateSeriesFactory(place=self.place, start_date=timezone.now() + relativedelta(months=2))

    def test_receive_series_changes(self):
        self.client = self.connect_as(self.member)

        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc) + relativedelta(months=2)
        self.series.start_date = date
        self.series.save()

        response = self.client.messages_by_topic.get('pickups:series')[0]
        self.assertEqual(parse(response['payload']['start_date']), date)

        self.assertEqual(len(self.client.messages), 1)

    def test_receive_series_delete(self):
        self.client = self.connect_as(self.member)

        id = self.series.id
        self.series.delete()

        response = self.client.messages_by_topic.get('pickups:series_deleted')[0]
        self.assertEqual(response['payload']['id'], id)

        self.assertEqual(len(self.client.messages), 1)


class FeedbackReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place)

    def test_receive_feedback_changes(self):
        self.client = self.connect_as(self.member)

        feedback = FeedbackFactory(given_by=self.member, about=self.pickup)

        response = self.client.messages_by_topic.get('feedback:feedback')[0]
        self.assertEqual(response['payload']['weight'], feedback.weight)

        self.assertEqual(len(self.client.messages), 1)


class FinishedPickupReceiverTest(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place, collectors=[self.member])

    def test_receive_history_and_notification(self):
        self.pickup.date = to_range(timezone.now() - relativedelta(days=1))
        self.pickup.save()

        self.client = self.connect_as(self.member)
        PickupDate.objects.process_finished_pickup_dates()

        history_response = next(m for m in self.client.messages if m['topic'] == 'history:history')
        self.assertEqual(history_response['payload']['typus'], 'PICKUP_DONE')

        history_response = next(m for m in self.client.messages if m['topic'] == 'notifications:notification')
        self.assertEqual(history_response['payload']['type'], 'feedback_possible')

        self.assertEqual(len(self.client.messages), 2, self.client.messages)


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

        response = self.client.messages_by_topic.get('auth:user')[0]
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

        self.assertEqual(len(self.client.messages), 1)

    def test_receive_changes_of_other_user(self):
        self.client = self.connect_as(self.member)

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        response = self.client.messages_by_topic.get('users:user')[0]
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
        self.assertIn('users:user', self.client.messages_by_topic.keys())

    def test_unrelated_user_receives_no_changes(self):
        self.client = self.connect_as(self.unrelated_user)

        self.member.display_name = faker.name()
        self.member.save()

        self.assertEqual(len(self.client.messages), 0)


class IssueReceiverTest(WSTestCase):
    def test_issue_created(self):
        member = VerifiedUserFactory()
        member2 = VerifiedUserFactory()
        group = GroupFactory(members=[member, member2])

        client = self.connect_as(member)
        IssueFactory(group=group, affected_user=member2, created_by=member)
        messages = client.messages_by_topic

        self.assertIn('issues:issue', messages)
        self.assertIn('conversations:conversation', messages)

        # TODO make it create less messages
        # self.assertEqual(len(client.messages), 2)
        # self.assertEqual(len(messages['issues:issue']), 1)
        # self.assertEqual(len(messages['conversations:conversation']), 1)


@patch('foodsaving.subscriptions.tasks.notify_subscribers')
class ReceiverPushTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.author = UserFactory()

        self.token = faker.uuid4()
        self.content = faker.text()

        # join a conversation
        self.conversation = ConversationFactory(participants=[self.user, self.author])

        # add a push subscriber
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            token=self.token,
            platform=PushSubscriptionPlatform.ANDROID.value,
        )

    def test_sends_to_push_subscribers(self, notify_subscribers):
        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)

        self.assertEqual(notify_subscribers.call_count, 2)
        kwargs = notify_subscribers.call_args_list[0][1]
        self.assertEqual(list(kwargs['subscriptions']), [self.subscription])
        self.assertEqual(kwargs['fcm_options']['message_title'], self.author.display_name)
        self.assertEqual(kwargs['fcm_options']['message_body'], self.content)

    def test_send_push_notification_if_active_channel_subscription(self, notify_subscribers):
        # add a channel subscription
        ChannelSubscription.objects.create(user=self.user, reply_channel='foo')
        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)

        kwargs = notify_subscribers.call_args_list[0][1]
        self.assertEqual(len(kwargs['subscriptions']), 1)
        kwargs = notify_subscribers.call_args_list[1][1]
        self.assertEqual(len(kwargs['subscriptions']), 0)

    def test_send_push_notification_if_channel_subscription_is_away(self, notify_subscribers):
        # add a channel subscription to prevent the push being sent
        ChannelSubscription.objects.create(user=self.user, reply_channel='foo', away_at=timezone.now())

        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)

        self.assertEqual(notify_subscribers.call_count, 2)
        kwargs = notify_subscribers.call_args_list[0][1]
        self.assertEqual(list(kwargs['subscriptions']), [self.subscription])
        self.assertEqual(kwargs['fcm_options']['message_title'], self.author.display_name)
        self.assertEqual(kwargs['fcm_options']['message_body'], self.content)


@patch('foodsaving.subscriptions.tasks.notify_subscribers')
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
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            token=self.token,
            platform=PushSubscriptionPlatform.ANDROID.value,
        )

    def test_sends_to_push_subscribers(self, notify_subscribers):
        # add a message to the conversation
        ConversationMessage.objects.create(conversation=self.conversation, content=self.content, author=self.author)

        self.assertEqual(notify_subscribers.call_count, 2)
        kwargs = notify_subscribers.call_args_list[0][1]
        self.assertEqual(list(kwargs['subscriptions']), [self.subscription])
        self.assertEqual(kwargs['fcm_options']['message_title'], self.group.name + ' / ' + self.author.display_name)
        self.assertEqual(kwargs['fcm_options']['message_body'], self.content)
