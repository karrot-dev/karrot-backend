from datetime import timedelta

from dateutil.parser import parse
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.applications.factories import ApplicationFactory
from karrot.conversations.factories import ConversationFactory
from karrot.conversations.models import ConversationParticipant, Conversation, ConversationMessage, \
    ConversationMessageReaction, ConversationNotificationStatus
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupStatus
from karrot.issues.factories import IssueFactory
from karrot.offers.factories import OfferFactory
from karrot.activities.factories import ActivityFactory
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import execute_scheduled_tasks_immediately
from karrot.users.factories import UserFactory, VerifiedUserFactory


class TestConversationsAPI(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant1 = UserFactory()
        cls.participant2 = UserFactory()
        cls.participant3 = UserFactory()
        cls.not_participant1 = UserFactory()
        cls.not_participant2 = UserFactory()
        cls.not_participant3 = UserFactory()
        cls.conversation1 = ConversationFactory()
        cls.conversation1.sync_users([cls.participant1, cls.participant2, cls.participant3])
        cls.conversation1.messages.create(author=cls.participant1, content='hello')
        cls.conversation2 = ConversationFactory()
        cls.conversation2.sync_users([cls.participant1])
        cls.conversation2.messages.create(author=cls.participant1, content='hello2')
        cls.conversation3 = ConversationFactory()  # conversation noone is in

    def test_conversations_list(self):
        self.conversation1.messages.create(author=self.participant1, content='yay')
        self.conversation1.messages.create(author=self.participant1, content='second!')
        conversation2 = ConversationFactory(participants=[self.participant1, self.participant2])
        conversation2.messages.create(author=self.participant1, content='yay')
        self.client.force_login(user=self.participant1)

        response = self.client.get('/api/conversations/', format='json')
        response_conversations = response.data['results']['conversations']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # is ordered by latest message first
        self.assertEqual(
            [conversation['id'] for conversation in response_conversations],
            [conversation2.id, self.conversation1.id, self.conversation2.id],
        )
        self.assertEqual(
            response.data['results']['meta'], {
                'conversations_marked_at': '0001-01-01T00:00:00Z',
                'threads_marked_at': '0001-01-01T00:00:00Z',
            }
        )

    def test_list_conversations_with_related_data_efficiently(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        activity = ActivityFactory(place=place)
        application = ApplicationFactory(user=UserFactory(), group=group)
        issue = IssueFactory(group=group)
        offer = OfferFactory(group=group)

        conversations = [t.conversation for t in (group, activity, application, issue, offer)]
        [c.sync_users([user]) for c in conversations]
        [c.messages.create(content='hey', author=user) for c in conversations]

        self.client.force_login(user=user)
        with self.assertNumQueries(16):
            response = self.client.get('/api/conversations/', {'group': group.id}, format='json')
        results = response.data['results']

        self.assertEqual(len(results['conversations']), len(conversations))
        self.assertEqual(results['activities'][0]['id'], activity.id)
        self.assertEqual(results['applications'][0]['id'], application.id)
        self.assertEqual(results['issues'][0]['id'], issue.id)
        self.assertEqual(results['offers'][0]['id'], offer.id)

    def test_retrieve_conversation_efficiently(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        conversation = group.conversation
        conversation.sync_users([user])
        conversation.messages.create(content='hey', author=user)

        self.client.force_login(user=user)
        with self.assertNumQueries(3):
            response = self.client.get('/api/conversations/{}/'.format(conversation.id), format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_only_unread_conversations(self):
        self.conversation1.messages.create(author=self.participant2, content='unread')
        self.client.force_login(user=self.participant1)
        response = self.client.get('/api/conversations/?exclude_read=True', format='json')
        conversations = response.data['results']['conversations']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(conversations[0]['id'], self.conversation1.id)
        self.assertEqual(len(conversations), 1)

    def test_list_messages(self):
        self.client.force_login(user=self.participant1)
        with self.assertNumQueries(6):
            response = self.client.get('/api/messages/?conversation={}'.format(self.conversation1.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['content'], 'hello')

    def test_get_message(self):
        self.client.force_login(user=self.participant1)
        message_id = self.conversation1.messages.first().id
        response = self.client.get('/api/messages/{}/'.format(message_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], message_id)

    def test_can_get_messages_for_all_conversations(self):
        self.client.force_login(user=self.participant1)
        response = self.client.get('/api/messages/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['content'], 'hello2')
        self.assertEqual(response.data['results'][1]['content'], 'hello')

    def test_cannot_get_messages_if_not_in_conversation(self):
        self.client.force_login(user=self.participant1)
        response = self.client.get('/api/messages/?conversation={}'.format(self.conversation3.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_same_error_if_conversation_does_not_exist_as_if_you_are_just_not_in_it(self):
        self.client.force_login(user=self.participant1)
        response = self.client.get('/api/messages/?conversation={}'.format(982398723), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_create_message(self):
        conversation = ConversationFactory(participants=[self.participant1])

        self.client.force_login(user=self.participant1)
        data = {'conversation': conversation.id, 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['content'], data['content'])
        self.assertEqual(conversation.messages.first().content, data['content'])
        self.assertEqual(conversation.messages.first().created_at, parse(response.data['created_at']), response.data)
        self.assertEqual(conversation.messages.first().id, response.data['id'])
        self.assertEqual(conversation.messages.first().author.id, response.data['author'])

    def test_cannot_create_message_without_specifying_conversation(self):
        self.client.force_login(user=self.participant1)
        data = {'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_message_if_not_in_conversation(self):
        self.client.force_login(user=self.participant1)
        data = {'conversation': self.conversation3.id, 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_mark_all_as_seen(self):
        self.client.force_login(user=self.participant1)

        response = self.client.post('/api/conversations/mark_conversations_seen/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        time1 = parse(response.data['conversations_marked_at'])
        self.assertLess(time1, timezone.now())

        # time should naturally increase each time we mark
        response = self.client.post('/api/conversations/mark_conversations_seen/')
        time2 = parse(response.data['conversations_marked_at'])
        self.assertLess(time1, time2)


class TestGroupPublicConversation(APITestCase):
    def test_can_access_messages_if_not_participant(self):
        user = UserFactory()
        author = UserFactory()
        group = GroupFactory(members=[user, author])
        activity = ActivityFactory(place=PlaceFactory(group=group))
        conversation = activity.conversation
        conversation.messages.create(author=author, content='asdf')

        self.client.force_login(user=user)
        response = self.client.get('/api/messages/?conversation={}'.format(conversation.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 1, response.data['results'])


class TestConversationThreadsAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.conversation = self.group.conversation
        self.thread = self.conversation.messages.create(author=self.user, content='yay')

    def create_reply(self, **kwargs):
        args = {
            'conversation': self.conversation,
            'author': self.user,
            'thread': self.thread,
            'content': 'my default reply',
        }
        args.update(kwargs)
        return ConversationMessage.objects.create(**args)

    def test_thread_reply(self):
        self.client.force_login(user=self.user)
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['thread'], self.thread.id)

    def test_reply_without_being_subscribed_to_conversation(self):
        self.conversation.conversationparticipant_set.filter(user=self.user).delete()

        self.client.force_login(user=self.user)
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertFalse(self.conversation.conversationparticipant_set.filter(user=self.user).exists())

    def test_thread_reply_a_few_times(self):
        self.client.force_login(user=self.user)
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['thread'], self.thread.id)

        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['thread'], self.thread.id)

        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['thread'], self.thread.id)

    def test_returns_thread_and_replies(self):
        self.client.force_login(user=self.user)
        another_thread = self.conversation.messages.create(author=self.user, content='my own thread')
        n = 5
        [self.create_reply(thread=another_thread) for _ in range(n)]

        response = self.client.get('/api/messages/?thread={}'.format(another_thread.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), n + 1)

    def test_list_my_recently_active_threads(self):
        most_recent_thread = self.conversation.messages.create(author=self.user, content='my own thread')
        self.create_reply(author=self.user2)
        another_thread = self.conversation.messages.create(author=self.user, content='my own thread')
        [self.create_reply(thread=another_thread) for _ in range(2)]
        self.conversation.messages.create(author=self.user, content='no replies yet')
        self.create_reply(thread=most_recent_thread)

        self.client.force_login(user=self.user)
        with self.assertNumQueries(6):
            response = self.client.get('/api/messages/my_threads/', format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual([thread['id'] for thread in results['threads']],
                         [most_recent_thread.id, another_thread.id, self.thread.id])
        self.assertEqual(len(results['threads']), len(results['messages']))

    def test_list_only_unread_threads(self):
        read_thread = self.conversation.messages.create(author=self.user, content='my own thread')
        self.create_reply(author=self.user, thread=read_thread)
        self.create_reply(author=self.user2)

        self.client.force_login(user=self.user)
        response = self.client.get('/api/messages/my_threads/?exclude_read=True', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        threads = response.data['results']['threads']
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]['id'], self.thread.id)

    def test_reply_adds_participant(self):
        self.client.force_login(user=self.user2)
        self.assertFalse(self.thread.participants.filter(user=self.user2).exists())
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(self.thread.participants.filter(user=self.user2).exists())

    def test_can_mute_thread(self):
        self.client.force_login(user=self.user)
        data = {'muted': True}
        self.create_reply()
        response = self.client.patch('/api/messages/{}/thread/'.format(self.thread.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        participant = self.thread.participants.get(user=self.user)
        self.assertEqual(participant.muted, True)

    def test_can_mark_seen_up_to(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply(author=self.user2)
        data = {'seen_up_to': reply.id}
        response = self.client.patch('/api/messages/{}/thread/'.format(self.thread.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], reply.id)
        self.assertEqual(response.data['unread_reply_count'], 0)
        participant = self.thread.participants.get(user=self.user2)
        self.assertEqual(participant.seen_up_to, reply)

    def test_cannot_mute_thread_with_no_replies(self):
        self.client.force_login(user=self.user)
        another_message = self.conversation.messages.create(author=self.user, content='boo')
        data = {'muted': True}
        response = self.client.patch('/api/messages/{}/thread/'.format(another_message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_edit_reply(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply()
        response = self.client.patch('/api/messages/{}/'.format(reply.id), {'content': 'edited!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], 'edited!')

    def test_can_react_to_reply(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply()
        response = self.client.post('/api/messages/{}/reactions/'.format(reply.id), {'name': 'smile'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_thread_meta_for_particiant(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply()
        response = self.client.get('/api/messages/', format='json')
        item = response.data['results'][0]
        self.assertEqual(item['thread'], self.thread.id)
        self.assertEqual(
            item['thread_meta'], {
                'is_participant': True,
                'participants': [self.user.id],
                'reply_count': 1,
                'seen_up_to': reply.id,
                'muted': False,
                'unread_reply_count': 0,
            }
        )

    def test_get_thread_meta_for_non_participant(self):
        self.client.force_login(user=self.user2)
        self.create_reply()
        response = self.client.get('/api/messages/', format='json')
        item = response.data['results'][0]
        self.assertEqual(item['thread'], self.thread.id)
        self.assertEqual(
            item['thread_meta'], {
                'is_participant': False,
                'participants': [self.user.id],
                'reply_count': 1,
            }
        )

    def test_cannot_create_private_conversation_threads(self):
        self.client.force_login(user=self.user)
        private_conversation = Conversation.objects.get_or_create_for_two_users(self.user, self.user2)
        private_message = private_conversation.messages.create(author=self.user, content='hey there, you look nice')
        data = {
            'conversation': private_conversation.id,
            'content': 'a nice message reply!',
            'thread': private_message.id,
        }
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fails_with_incorrect_conversation(self):
        self.client.force_login(user=self.user)
        another_conversation = Conversation.objects.get_or_create_for_two_users(self.user, self.user2)
        data = {
            'conversation': another_conversation.id,
            'content': 'a nice message reply!',
            'thread': self.thread.id,
        }
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_reply_to_replies(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply()
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': reply.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_move_replies_between_threads(self):
        self.client.force_login(user=self.user)
        another_message = self.conversation.messages.create(author=self.user, content='yay')
        reply = self.create_reply()
        data = {'thread': another_message.id}
        response = self.client.patch('/api/messages/{}/'.format(reply.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_reply_notifications(self):
        mail.outbox = []
        with execute_scheduled_tasks_immediately():
            self.create_reply(author=self.user2)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.thread.content, mail.outbox[0].subject)
        self.assertIn('In reply to', mail.outbox[0].body)


class TestConversationsSeenUpToAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.conversation = ConversationFactory(participants=[self.user, self.user2])
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)

    def test_message_marked_seen_for_author(self):
        message = self.conversation.messages.create(author=self.user, content='yay')
        self.client.force_login(user=self.user)

        response = self.client.get('/api/conversations/{}/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], message.id)
        self.assertEqual(response.data['unread_message_count'], 0)

    def test_conversation_get(self):
        message = self.conversation.messages.create(author=self.user2, content='yay')
        self.client.force_login(user=self.user)

        response = self.client.get('/api/conversations/{}/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], None)
        self.assertEqual(response.data['unread_message_count'], 1)
        self.assertEqual(response.data['type'], None)

        self.participant.seen_up_to = message
        self.participant.save()

        response = self.client.get('/api/conversations/{}/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], message.id)
        self.assertEqual(response.data['unread_message_count'], 0)

    def test_conversation_list(self):
        message = self.conversation.messages.create(author=self.user, content='yay')
        self.client.force_login(user=self.user)

        self.participant.seen_up_to = message
        self.participant.save()

        response = self.client.get('/api/conversations/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results']['conversations'][0]['seen_up_to'], message.id)

    def test_mark_seen_up_to(self):
        message = self.conversation.messages.create(author=self.user2, content='yay')
        self.client.force_login(user=self.user)

        response = self.client.get('/api/conversations/{}/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], None)

        data = {'seen_up_to': message.id}
        response = self.client.patch('/api/conversations/{}/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], message.id)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.seen_up_to, message)

    def test_mark_seen_up_to_fails_for_invalid_id(self):
        self.client.force_login(user=self.user)
        data = {'seen_up_to': 9817298172}
        response = self.client.patch('/api/conversations/{}/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['seen_up_to'][0], 'Invalid pk "{}" - object does not exist.'.format(data['seen_up_to'])
        )

    def test_mark_seen_up_to_fails_for_message_in_other_conversation(self):
        conversation = ConversationFactory(participants=[self.user])

        message = conversation.messages.create(author=self.user, content='yay')
        self.client.force_login(user=self.user)

        data = {'seen_up_to': message.id}
        response = self.client.patch('/api/conversations/{}/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['seen_up_to'][0], 'Must refer to a message in the conversation')


class TestConversationsEmailNotificationsAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user])
        self.conversation = self.group.conversation
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)

    def test_mute(self):
        participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.assertFalse(participant.muted)

        self.client.force_login(user=self.user)

        data = {'notifications': ConversationNotificationStatus.MUTED.value}
        response = self.client.patch('/api/conversations/{}/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['notifications'], ConversationNotificationStatus.MUTED.value)

        participant.refresh_from_db()
        self.assertTrue(participant.muted)

    def test_unmute(self):
        participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        participant.muted = True
        participant.save()
        self.assertTrue(participant.muted)

        self.client.force_login(user=self.user)

        data = {'notifications': ConversationNotificationStatus.ALL.value}
        response = self.client.patch('/api/conversations/{}/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['notifications'], ConversationNotificationStatus.ALL.value)

        participant.refresh_from_db()
        self.assertFalse(participant.muted)

    def test_send_email_notifications(self):
        users = [VerifiedUserFactory() for _ in range(3)]
        [self.group.add_member(u) for u in users]

        mail.outbox = []
        with execute_scheduled_tasks_immediately():
            ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')

        actual_recipients = set(m.to[0] for m in mail.outbox)
        expected_recipients = set(u.email for u in users)

        self.assertEqual(actual_recipients, expected_recipients)

        self.assertEqual(len(mail.outbox), 3)

    def test_exclude_unverified_addresses(self):
        user = UserFactory()  # not verified
        self.group.add_member(user)

        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')
        self.assertEqual(len(mail.outbox), 0)


class TestConversationsMessageReactionsPostAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.conversation = Conversation.objects.get_or_create_for_target(self.group)
        self.conversation.join(self.user)
        self.conversation.join(self.user2)
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.message = self.conversation.messages.create(author=self.user, content='hello')
        self.reaction = self.message.reactions.create(user=self.user, name='thumbsdown')

        self.group2 = GroupFactory(members=[self.user])
        self.conversation2 = Conversation.objects.get_or_create_for_target(self.group2)
        self.conversation2.join(self.user)
        self.message2 = self.conversation2.messages.create(author=self.user, content='hello2')

    def test_not_logged(self):
        """Non-authenticated user can't add emoji."""

        # log in is missing

        data = {'name': 'thumbsup'}
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_emoji_to_message_of_other_group(self):
        """It should be impossible to add emoji to a message from group user is not member of."""

        # log in as user who didn't join the conversation
        self.client.force_login(user=self.user2)
        data = {'name': 'thumbsup'}
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message2.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_to_message_with_invalid_id(self):
        """It should fail predictably when message has invalid id. (respond status 404)"""
        self.client.force_login(user=self.user)
        data = {'name': 'thumbsup'}
        response = self.client.post('/api/messages/{}/reactions/'.format('invalid'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_nonexistent_emoji(self):
        """It should be impossible to add an unsupported emoji. (respond 400)"""
        self.client.force_login(user=self.user)
        data = {'name': 'nonexistent_emoji'}
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_request_fails(self):
        """If no emoji is given, the request should fail (respond 400)"""
        self.client.force_login(user=self.user)
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reaction_to_nonexistent_message(self):
        """It should error with 404 when trying to react to nonexistent message."""

        # log in as user who didn't join the conversation
        self.client.force_login(user=self.user)

        data = {'name': 'thumbsup'}
        response = self.client.post('/api/messages/{}/reactions/'.format(1735), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_dont_react_twice_with_the_same_emoji(self):
        """Can not react with the same emoji twice."""
        self.client.force_login(user=self.user)
        data = {'name': 'thumbsup'}

        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_react_to_message_with_emoji(self):
        """User who can participate in conversation can react to a message with emoji."""
        self.client.force_login(user=self.user)
        data = {'name': 'tada'}
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'tada')
        self.assertTrue(
            ConversationMessageReaction.objects.filter(user=self.user, message=self.message, name='tada').exists()
        )

    def test_emojis_save_base_form_of_name(self):
        """Emojis are saved in their base form (i.e. +1 -> thumbsup)"""

        # log in
        self.client.force_login(user=self.user)
        data = {'name': '+1'}
        response = self.client.post('/api/messages/{}/reactions/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'thumbsup')

        # and the base form can't be saved now
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id), {'name': 'thumbsup'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_react_with_different_emoji(self):
        """Can react multiple times with different emoji."""
        self.client.force_login(user=self.user)

        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id), {'name': 'thumbsup'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # second request with different emoji is ok
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id), {'name': 'tada'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_include_reactions_in_message(self):
        """When reading conversations, include reactions in the response for every message"""

        # add a few more reactions
        self.reaction = self.message.reactions.create(user=self.user, name='thumbsup')
        self.reaction = self.message.reactions.create(user=self.user2, name='thumbsup')

        self.client.force_login(user=self.user)
        response = self.client.get('/api/messages/?conversation={}'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(len(response.data['results'][0]['reactions']), 3)


class TestConversationsMessageReactionsDeleteAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.conversation = Conversation.objects.get_or_create_for_target(self.group)
        self.conversation.join(self.user)
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.message = self.conversation.messages.create(author=self.user, content='hello')
        self.reaction = self.message.reactions.create(user=self.user, name='thumbsup')

        self.group2 = GroupFactory(members=[self.user])
        self.conversation2 = Conversation.objects.get_or_create_for_target(self.group2)
        self.conversation2.join(self.user)
        self.message2 = self.conversation2.messages.create(author=self.user, content='hello2')

    def test_remove_reaction_not_authenticated(self):
        """Unauthenticated user can't remove a reaction."""

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_not_in_conversation_cant_remove_reaction(self):
        """User can't remove a reaction of message from alien conversation, but fails with 403."""
        self.client.force_login(user=self.user2)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_reaction_invalid_message_id(self):
        """When message has invalid name, it should fail predictably. (404)"""
        self.client.force_login(user=self.user)

        response = self.client.delete('/api/messages/{}/reactions/{}/'.format('hello', 'thumbsup'), format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_reaction_invalid_emoji_name(self):
        """When emoji has invalid name, response should be 400."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'invalid_emoji'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_reaction_message_not_exist(self):
        """When message with given id doesn't exist, respond with 404."""
        self.client.force_login(user=self.user)

        response = self.client.delete('/api/messages/{}/reactions/{}/'.format(7321, 'thumbsup'), format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_nonexisting_reaction(self):
        """When we try to remove nonexisting reaction, response should be 404."""
        self.client.force_login(user=self.user)

        response = self.client.delete('/api/messages/{}/reactions/{}/'.format(self.message.id, '-1'), format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_existing_reaction(self):
        """User can remove her reaction."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_remove_non_base_name(self):
        """Can remove +1, -1, which removes thumbsup, thumbsdown, etc."""
        self.client.force_login(user=self.user)

        response = self.client.delete('/api/messages/{}/reactions/{}/'.format(self.message.id, '+1'), format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TestConversationsMessageEditAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.conversation = Conversation.objects.get_or_create_for_target(self.group)
        self.conversation.join(self.user)
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.message = self.conversation.messages.create(author=self.user, content='hello')

        self.group2 = GroupFactory(members=[self.user, self.user2])
        self.conversation2 = Conversation.objects.get_or_create_for_target(self.group2)
        self.conversation2.join(self.user)
        self.conversation2.join(self.user2)
        self.message2 = self.conversation2.messages.create(author=self.user, content='hello2')
        self.message3 = self.conversation2.messages.create(
            author=self.user,
            content='hello3',
            created_at=(timezone.now() - timedelta(days=10)),
        )

    def test_edit_message(self):
        self.client.force_login(user=self.user)
        data = {'content': 'hi'}
        now = timezone.now()
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertGreater(parse(response.data['edited_at']), now)

    def test_cannot_update_message_without_specifying_content(self):
        self.client.force_login(user=self.user)
        data = {'content': ''}
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_update_message_if_not_in_conversation(self):
        self.client.force_login(user=self.user2)
        data = {'content': 'a nice message'}
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_update_message_if_not_message_author(self):
        self.client.force_login(user=self.user2)
        data = {'content': 'a nicer message'}
        response = self.client.patch('/api/messages/{}/'.format(self.message2.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_update_message_if_past_10_days(self):
        self.client.force_login(user=self.user)
        data = {'content': 'a nicer message'}
        response = self.client.patch('/api/messages/{}/'.format(self.message3.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestWallMessagesUpdateStatus(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.conversation = Conversation.objects.get_or_create_for_target(self.group)
        self.conversation.join(self.user)

    def test_wall_message_activates_inactive_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.user)
        data = {'conversation': self.conversation.id, 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['content'], data['content'])
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)


class TestClosedConversation(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.conversation = ConversationFactory(participants=[self.user], is_closed=True)

    def test_write_message_in_closed_conversation_fails(self):
        self.client.force_login(user=self.user)
        response = self.client.post('/api/messages/', {'conversation': self.conversation.id, 'content': 'hello'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)


class TestPrivateConversationAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()

    def test_cannot_leave_private_conversation(self):
        self.client.force_login(user=self.user)
        private_conversation = Conversation.objects.get_or_create_for_two_users(self.user, self.user2)
        response = self.client.patch(
            '/api/conversations/{}/'.format(private_conversation.id), {
                'notifications': ConversationNotificationStatus.NONE.value,
            },
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['notifications'], ['You cannot leave a private conversation'])
