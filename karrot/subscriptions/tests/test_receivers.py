import itertools
import os
import pathlib
from operator import itemgetter
from shutil import copyfile
from unittest.mock import patch

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.utils.crypto import get_random_string

from karrot.applications.factories import ApplicationFactory
from karrot.conversations.factories import ConversationFactory
from karrot.conversations.models import ConversationMessage, \
    ConversationMessageReaction, ConversationNotificationStatus
from karrot.groups import roles
from karrot.groups.factories import GroupFactory
from karrot.groups.models import Trust, GroupMembership
from karrot.invitations.models import Invitation
from karrot.issues.factories import IssueFactory, vote_for_further_discussion
from karrot.notifications.models import Notification
from karrot.offers.factories import OfferFactory
from karrot.activities.factories import FeedbackFactory, ActivityFactory, \
    ActivitySeriesFactory
from karrot.activities.models import Activity, to_range
from karrot.places.factories import PlaceFactory
from karrot.subscriptions.models import ChannelSubscription, \
    PushSubscription, PushSubscriptionPlatform
from karrot.users.factories import UserFactory, VerifiedUserFactory
from karrot.utils.tests.fake import faker
from karrot.utils.tests.images import image_path


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
            'images': [],
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

    def reset_messages(self):
        self.send_in_channel_mock.reset_mock()

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
        self.send_in_channel_patcher = patch('karrot.subscriptions.receivers.send_in_channel')
        self.send_in_channel_mock = self.send_in_channel_patcher.start()
        self.addCleanup(self.send_in_channel_patcher.stop)

    def connect_as(self, user):
        client = WSClient(self.send_in_channel_mock)
        client.connect_as(user)
        return client


class WSTransactionTestCase(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.send_in_channel_patcher = patch('karrot.subscriptions.receivers.send_in_channel')
        self.send_in_channel_mock = self.send_in_channel_patcher.start()
        self.addCleanup(self.send_in_channel_patcher.stop)

    def connect_as(self, user):
        client = WSClient(self.send_in_channel_mock)
        client.connect_as(user)
        return client


class ConversationReceiverTests(WSTransactionTestCase):
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
        ws_messages = client.messages_by_topic
        self.assertEqual(len(ws_messages['conversations:conversation']), 1, ws_messages['conversations:conversation'])
        self.assertEqual(len(ws_messages['conversations:message']), 1, ws_messages['conversations:message'])
        self.assertEqual(len(ws_messages['status']), 1, ws_messages['status'])
        self.assertEqual(
            ws_messages['status'][0]['payload'], {
                'unseen_conversation_count': 1,
                'unseen_thread_count': 0,
                'has_unread_conversations_or_threads': True,
                'groups': {},
                'places': {},
            }
        )

        response = ws_messages['conversations:message'][0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(message))

        # and they should get an updated conversation object
        response = ws_messages['conversations:conversation'][0]
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
        author = UserFactory()
        # join a conversation
        conversation = ConversationFactory(participants=[user, author])
        # write a message
        ConversationMessage.objects.create(conversation=conversation, content='yay', author=author)

        # login and connect
        client = self.connect_as(user)

        conversation.leave(user)
        messages = client.messages_by_topic
        self.assertEqual(len(messages['conversations:leave']), 1, messages['conversations:leave'])
        self.assertEqual(messages['conversations:leave'][0]['payload'], {'id': conversation.id})

        self.assertEqual(len(messages['status']), 1, messages['status'])
        self.assertEqual(
            messages['status'][0]['payload'], {
                'unseen_thread_count': 0,
                'unseen_conversation_count': 0,
                'has_unread_conversations_or_threads': False,
                'groups': {},
                'places': {},
            }
        )

    def test_other_participants_receive_update_on_join(self):
        user = UserFactory()
        joining_user = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[user])
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

        response = client.messages_by_topic['conversations:conversation'][0]
        self.assertEqual(response['payload']['participants'], [user.id])

    def test_conversation_marked_as_seen(self):
        user, author = [UserFactory() for _ in range(2)]
        conversation = ConversationFactory(participants=[user, author])
        message = ConversationMessage.objects.create(conversation=conversation, content='yay', author=author)
        participant = conversation.conversationparticipant_set.get(user=user)
        client = self.connect_as(user)

        participant.seen_up_to = message
        participant.save()

        messages = client.messages_by_topic
        self.assertEqual(len(messages['status']), 1, messages['status'])
        self.assertEqual(
            messages['status'][0]['payload'], {
                'unseen_thread_count': 0,
                'unseen_conversation_count': 0,
                'has_unread_conversations_or_threads': False,
                'groups': {},
                'places': {},
            }
        )


class ConversationThreadReceiverTests(WSTransactionTestCase):
    def test_receives_messages(self):
        self.maxDiff = None
        op_user = UserFactory()  # op: original post
        author = UserFactory()  # this user will reply to op

        conversation = ConversationFactory(participants=[op_user, author])
        thread = conversation.messages.create(author=op_user, content='yay')

        # login and connect
        op_client = self.connect_as(op_user)
        author_client = self.connect_as(author)

        reply = ConversationMessage.objects.create(
            conversation=conversation,
            thread=thread,
            content='really yay?',
            author=author,
        )

        op_messages = op_client.messages_by_topic

        # updated status
        self.assertEqual(len(op_messages['status']), 1, op_messages['status'])
        self.assertEqual(
            op_messages['status'][0]['payload'], {
                'unseen_thread_count': 1,
                'unseen_conversation_count': 0,
                'has_unread_conversations_or_threads': True,
                'groups': {},
                'places': {},
            }
        )

        # user receive message
        response = op_messages['conversations:message'][0]
        parse_dates(response)
        self.assertEqual(response, make_conversation_message_broadcast(
            reply,
            thread=thread.id,
        ))

        # and they should get an updated thread object
        response = op_messages['conversations:message'][1]
        parse_dates(response)
        self.assertEqual(
            response,
            make_conversation_message_broadcast(
                thread,
                thread_meta={
                    'is_participant': True,
                    'muted': False,
                    'participants': [op_user.id, author.id],
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
                    'participants': [op_user.id, author.id],
                    'reply_count': 1,
                    'seen_up_to': reply.id,
                    'unread_reply_count': 0,
                },
                updated_at=response['payload']['updated_at'],  # TODO fix test
            )
        )

    def test_thread_marked_as_seen(self):
        author, op_author = [UserFactory() for _ in range(2)]
        conversation = ConversationFactory(participants=[author, op_author])
        thread = ConversationMessage.objects.create(conversation=conversation, content='yay', author=op_author)
        reply = ConversationMessage.objects.create(
            conversation=conversation,
            thread=thread,
            content='really yay?',
            author=author,
        )
        participant = thread.participants.get(user=op_author)
        client = self.connect_as(op_author)

        participant.seen_up_to = reply
        participant.save()

        messages = client.messages_by_topic
        self.assertEqual(len(messages['status']), 1, messages['status'])
        self.assertEqual(
            messages['status'][0]['payload'], {
                'unseen_thread_count': 0,
                'unseen_conversation_count': 0,
                'has_unread_conversations_or_threads': False,
                'groups': {},
                'places': {},
            }
        )


class ConversationMessageReactionReceiverTests(WSTransactionTestCase):
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
        client = self.connect_as(self.member)

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = client.messages_by_topic.get('groups:group_detail')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' in response['payload'])

        response = client.messages_by_topic.get('groups:group_preview')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(client.messages), 2)

    def test_receive_group_changes_as_nonmember(self):
        client = self.connect_as(self.user)

        name = faker.name()
        self.group.name = name
        self.group.save()

        response = client.messages_by_topic.get('groups:group_preview')[0]
        self.assertEqual(response['payload']['name'], name)
        self.assertTrue('description' not in response['payload'])

        self.assertEqual(len(client.messages), 1)


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
        # Clean up notifications from group setup, to prevent notification_deleted messages
        Notification.objects.all().delete()
        client = self.connect_as(self.member)

        self.group.remove_member(self.member)

        response = client.messages_by_topic.get('groups:group_preview')[0]
        self.assertNotIn(self.user.id, response['payload']['members'])
        self.assertNotIn('memberships', response['payload'])
        self.assertEqual([m['topic'] for m in client.messages], [
            'history:history',
            'conversations:leave',
            'conversations:conversation',
            'status',
            'groups:group_preview',
        ])

        status_messages = client.messages_by_topic['status']
        self.assertEqual(len(status_messages), 1, status_messages)
        self.assertEqual(
            status_messages[0]['payload'], {
                'unseen_conversation_count': 0,
                'unseen_thread_count': 0,
                'has_unread_conversations_or_threads': False,
                'groups': {
                    self.group.id: {
                        'unread_wall_message_count': 0
                    }
                },
                'places': {},
            }
        )

    def test_receive_group_roles_update(self):
        membership = self.group.add_member(self.user)
        client = self.connect_as(self.member)

        membership.add_roles([roles.GROUP_EDITOR])
        membership.save()

        response = client.messages_by_topic.get('groups:group_detail')[0]
        self.assertIn(roles.GROUP_EDITOR, response['payload']['memberships'][self.user.id]['roles'])

        self.assertEqual([m['topic'] for m in client.messages], [
            'notifications:notification',
            'status',
            'groups:group_detail',
        ])


class ApplicationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.member])
        Notification.objects.all().delete()

    def test_member_receives_application_create(self):
        client = self.connect_as(self.member)

        application = ApplicationFactory(user=self.user, group=self.group)

        messages = client.messages_by_topic['applications:update']
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['payload']['id'], application.id)

        messages = client.messages_by_topic['status']
        self.assertEqual(len(messages), 2, messages)
        # We told the user that we have 1 pending application
        self.assertEqual(messages[0]['payload'], {'groups': {self.group.id: {'pending_application_count': 1}}})
        # "There is an application for your group!"
        self.assertEqual(messages[1]['payload'], {'unseen_notification_count': 1})

        client.reset_messages()
        # mark notification as read
        meta = self.member.notificationmeta
        meta.marked_at = timezone.now()
        meta.save()

        messages = client.messages_by_topic['status']
        self.assertEqual(len(messages), 1, messages)
        self.assertEqual(messages[0]['payload'], {'unseen_notification_count': 0})

    def test_member_receives_application_update(self):
        application = ApplicationFactory(user=self.user, group=self.group)

        client = self.connect_as(self.member)

        application.status = 'accepted'
        application.save()

        messages = client.messages_by_topic['applications:update']
        self.assertEqual(len(messages), 1)
        response = messages[0]
        self.assertEqual(response['payload']['id'], application.id)

        messages = client.messages_by_topic['status']
        self.assertEqual(len(messages), 2, messages)
        # No pending applications
        self.assertEqual(messages[1]['payload'], {'groups': {self.group.id: {'pending_application_count': 0}}})
        # Notification gets deleted because application has been accepted
        self.assertEqual(messages[0]['payload'], {'unseen_notification_count': 0})

    def test_applicant_receives_application_update(self):
        application = ApplicationFactory(user=self.user, group=self.group)
        Notification.objects.all().delete()

        client = self.connect_as(self.user)

        application.status = 'accepted'
        application.save()

        messages = client.messages_by_topic['applications:update']
        self.assertEqual(len(messages), 1)
        response = messages[0]
        self.assertEqual(response['payload']['id'], application.id)

        messages = client.messages_by_topic['status']
        self.assertEqual(len(messages), 1, messages)
        # "Your application has been accepted"
        self.assertEqual(messages[0]['payload'], {'unseen_notification_count': 1})


class InvitationReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])

    def test_receive_invitation_updates(self):
        client = self.connect_as(self.member)

        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)

        response = client.messages_by_topic.get('invitations:invitation')[0]
        self.assertEqual(response['payload']['email'], invitation.email)

        self.assertEqual(len(client.messages), 1)

    def test_receive_invitation_accept(self):
        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.member)
        user = UserFactory()

        client = self.connect_as(self.member)

        id = invitation.id
        invitation.accept(user)

        response = next(r for r in client.messages if r['topic'] == 'invitations:invitation_accept')
        self.assertEqual(response['payload']['id'], id)


class PlaceReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)

    def test_receive_place_changes(self):
        client = self.connect_as(self.member)

        name = faker.name()
        self.place.name = name
        self.place.save()

        response = client.messages_by_topic.get('places:place')[0]
        self.assertEqual(response['payload']['name'], name)

        self.assertEqual(len(client.messages), 1)


class ActivityReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place)

    def test_receive_activity_changes(self):
        client = self.connect_as(self.member)

        # change property
        date = to_range(faker.future_datetime(end_date='+30d', tzinfo=timezone.utc))
        self.activity.date = date
        self.activity.save()

        response = client.messages_by_topic.get('activities:activity')[0]
        self.assertEqual(parse(response['payload']['date'][0]), date.start)

        # join
        client = self.connect_as(self.member)
        self.activity.add_participant(self.member)

        response = client.messages_by_topic.get('activities:activity')[0]
        self.assertEqual(response['payload']['participants'], [self.member.id])

        response = client.messages_by_topic.get('conversations:conversation')[0]
        self.assertEqual(response['payload']['participants'], [self.member.id])

        # leave
        client = self.connect_as(self.member)
        self.activity.remove_participant(self.member)

        response = client.messages_by_topic.get('activities:activity')[0]
        self.assertEqual(response['payload']['participants'], [])

        self.assertIn('conversations:leave', client.messages_by_topic.keys())

    def test_mark_as_done(self):
        self.activity.add_participant(self.member)
        Notification.objects.all().delete()
        client = self.connect_as(self.member)
        self.activity.is_done = True
        self.activity.save()

        messages = client.messages_by_topic
        self.assertEqual(len(messages['status']), 2, messages['status'])
        self.assertEqual(messages['status'][0]['payload'], {'unseen_notification_count': 1})
        self.assertEqual(messages['status'][1]['payload'], {'groups': {self.group.id: {'feedback_possible_count': 1}}})
        self.assertEqual(len(messages['notifications:notification']), 1, messages['notifications:notification'])
        self.assertEqual(messages['notifications:notification'][0]['payload']['type'], 'feedback_possible')

    def test_receive_activity_delete(self):
        client = self.connect_as(self.member)

        activity_id = self.activity.id
        self.activity.delete()

        response = client.messages_by_topic.get('activities:activity_deleted')[0]
        self.assertEqual(response['payload']['id'], activity_id)

        self.assertEqual(len(client.messages), 1)


class ActivitySeriesReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)

        # Create far in the future to generate no activities
        # They would lead to interfering websocket messages
        self.series = ActivitySeriesFactory(place=self.place, start_date=timezone.now() + relativedelta(months=2))

    def test_receive_series_changes(self):
        client = self.connect_as(self.member)

        date = faker.future_datetime(end_date='+30d', tzinfo=timezone.utc) + relativedelta(months=2)
        self.series.start_date = date
        self.series.save()

        response = client.messages_by_topic.get('activities:series')[0]
        self.assertEqual(parse(response['payload']['start_date']), date)

        self.assertEqual(len(client.messages), 1)

    def test_receive_series_delete(self):
        client = self.connect_as(self.member)

        id = self.series.id
        self.series.delete()

        response = client.messages_by_topic.get('activities:series_deleted')[0]
        self.assertEqual(response['payload']['id'], id)

        self.assertEqual(len(client.messages), 1)


class OfferReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.other_member = UserFactory()
        self.group = GroupFactory(members=[self.member, self.other_member])
        self.offer = OfferFactory(group=self.group, user=self.member)

    def test_receive_offer_changes(self):
        client = self.connect_as(self.member)

        self.offer.name = faker.name()
        self.offer.save()
        response = client.messages_by_topic.get('offers:offer')[0]
        self.assertEqual(response['payload']['name'], self.offer.name)
        self.assertEqual(len(client.messages), 1)

    def test_receiver_offer_deleted(self):
        client = self.connect_as(self.member)

        id = self.offer.id
        self.offer.delete()

        response = client.messages_by_topic.get('offers:offer_deleted')[0]
        self.assertEqual(response['payload']['id'], id)
        self.assertEqual(len(client.messages), 1)

    def test_receiver_offer_deleted_for_other_user_when_archived(self):
        client = self.connect_as(self.other_member)

        id = self.offer.id
        self.offer.archive()

        response = client.messages_by_topic.get('offers:offer_deleted')[0]
        self.assertEqual(response['payload']['id'], id)
        self.assertEqual(len(client.messages), 1)

    def test_receiver_offer_updated_for_other_user_when_archived_if_in_conversation(self):
        client = self.connect_as(self.other_member)
        self.offer.conversation.join(self.other_member)
        client.reset_messages()  # otherwise we have various conversation related messages

        id = self.offer.id
        self.offer.archive()

        response = client.messages_by_topic.get('offers:offer')[0]
        self.assertEqual(response['payload']['id'], id)
        self.assertEqual(len(client.messages), 1)


class FeedbackReceiverTests(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place)

    def test_receive_feedback_changes(self):
        client = self.connect_as(self.member)

        feedback = FeedbackFactory(given_by=self.member, about=self.activity)

        response = client.messages_by_topic.get('feedback:feedback')[0]
        self.assertEqual(response['payload']['weight'], feedback.weight)

        self.assertEqual([m['topic'] for m in client.messages], [
            'feedback:feedback',
            'status',
        ], client.messages)

        self.assertEqual(
            client.messages_by_topic['status'][0]['payload'],
            {'groups': {
                self.group.id: {
                    'feedback_possible_count': 0
                }
            }}
        )


class FinishedActivityReceiverTest(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, participants=[self.member])

    def test_receive_history_and_notification(self):
        self.activity.date = to_range(timezone.now() - relativedelta(days=1))
        self.activity.save()

        Notification.objects.all().delete()

        client = self.connect_as(self.member)
        Activity.objects.process_finished_activities()

        messages_by_topic = client.messages_by_topic

        response = messages_by_topic['history:history'][0]
        self.assertEqual(response['payload']['typus'], 'ACTIVITY_DONE')

        response = messages_by_topic['notifications:notification'][0]
        self.assertEqual(response['payload']['type'], 'feedback_possible')

        status_messages = messages_by_topic['status']
        self.assertEqual(len(status_messages), 2)
        self.assertEqual(status_messages[0]['payload'], {'unseen_notification_count': 1})
        self.assertEqual(status_messages[1]['payload'], {'groups': {self.group.id: {'feedback_possible_count': 1}}})

        self.assertEqual(len(client.messages), 4, client.messages)

    def test_receive_dismissed_feedback(self):
        self.activity.date = to_range(timezone.now() - relativedelta(days=1))
        self.activity.save()

        client = self.connect_as(self.member)
        Activity.objects.process_finished_activities()

        messages_by_topic = client.messages_by_topic

        status_messages = messages_by_topic['status']
        self.assertEqual(len(status_messages), 2)
        self.assertEqual(status_messages[1]['payload'], {'groups': {self.group.id: {'feedback_possible_count': 1}}})

        self.activity.dismiss_feedback(self.member)

        messages_by_topic = client.messages_by_topic

        status_messages = messages_by_topic['status']
        self.assertEqual(len(status_messages), 3)
        self.assertEqual(status_messages[2]['payload'], {'groups': {self.group.id: {'feedback_possible_count': 0}}})


class UserReceiverTest(WSTestCase):
    def setUp(self):
        super().setUp()
        self.member = UserFactory()
        self.other_member = UserFactory()
        self.unrelated_user = UserFactory()
        self.group = GroupFactory(members=[self.member, self.other_member])
        pathlib.Path(settings.MEDIA_ROOT).mkdir(exist_ok=True)
        copyfile(image_path, os.path.join(settings.MEDIA_ROOT, 'photo.jpg'))
        self.member.photo = 'photo.jpg'
        self.member.save()
        self.other_member.photo = 'photo.jpg'
        self.other_member.save()

    def test_receive_own_user_changes(self):
        client = self.connect_as(self.member)

        name = faker.name()
        self.member.display_name = name
        self.member.save()

        response = client.messages_by_topic.get('auth:user')[0]
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

        self.assertEqual(len(client.messages), 1)

    def test_receive_changes_of_other_user(self):
        client = self.connect_as(self.member)

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        response = client.messages_by_topic.get('users:user')[0]
        self.assertEqual(response['payload']['display_name'], name)
        self.assertTrue('current_group' not in response['payload'])
        self.assertTrue(response['payload']['photo_urls']['full_size'].startswith(settings.HOSTNAME))

        self.assertEqual(len(client.messages), 1)

    def test_do_not_send_too_many_updates(self):
        [GroupFactory(members=[self.member, self.other_member]) for _ in range(3)]

        client = self.connect_as(self.member)

        name = faker.name()
        self.other_member.display_name = name
        self.other_member.save()

        self.assertEqual(len(client.messages), 1)
        self.assertIn('users:user', client.messages_by_topic.keys())

    def test_unrelated_user_receives_no_changes(self):
        client = self.connect_as(self.unrelated_user)

        self.member.display_name = faker.name()
        self.member.save()

        self.assertEqual(len(client.messages), 0)


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

        self.assertEqual(len(messages['issues:issue']), 1)
        # TODO make it create less messages
        # self.assertEqual(len(messages['conversations:conversation']), 1, messages['conversations:conversation'])
        # self.assertEqual(len(client.messages), 2)

    def test_vote(self):
        member = VerifiedUserFactory()
        member2 = VerifiedUserFactory()
        group = GroupFactory(members=[member, member2])
        issue = IssueFactory(group=group, affected_user=member2, created_by=member)

        client = self.connect_as(member)
        vote_for_further_discussion(voting=issue.latest_voting(), user=member)

        messages = client.messages_by_topic
        self.assertEqual(len(client.messages), 1)
        self.assertEqual(len(messages['issues:issue']), 1)

    def test_delete_vote(self):
        member = VerifiedUserFactory()
        member2 = VerifiedUserFactory()
        group = GroupFactory(members=[member, member2])
        issue = IssueFactory(group=group, affected_user=member2, created_by=member)
        vote_for_further_discussion(voting=issue.latest_voting(), user=member)

        client = self.connect_as(member)
        issue.latest_voting().delete_votes(user=member)

        messages = client.messages_by_topic
        self.assertEqual(len(client.messages), 1)
        self.assertEqual(len(messages['issues:issue']), 1)


@patch('karrot.subscriptions.tasks.notify_subscribers')
class ReceiverPushTests(TransactionTestCase):
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


@patch('karrot.subscriptions.tasks.notify_subscribers')
class GroupConversationReceiverPushTests(TransactionTestCase):
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


class TrustReceiverTest(WSTestCase):

    def test_revoke_trust(self):
        trust_receiver = UserFactory()
        trust_giver = UserFactory()
        group = GroupFactory(members=[trust_giver, trust_receiver])

        client = self.connect_as(trust_giver)

        membership = GroupMembership.objects.get(user=trust_receiver, group=group)
        trust = Trust.objects.create(membership=membership, given_by=trust_giver)

        trust.delete()

        responses = client.messages_by_topic.get('groups:group_detail')
        self.assertEqual(responses[0]['payload']['memberships'][trust_receiver.id]['trusted_by'], [trust_giver.id])
        self.assertEqual(responses[1]['payload']['memberships'][trust_receiver.id]['trusted_by'], [])
