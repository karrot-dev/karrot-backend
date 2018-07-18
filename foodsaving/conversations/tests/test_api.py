from datetime import timedelta

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import ConversationParticipant, Conversation, ConversationMessage, \
    ConversationMessageReaction
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupStatus
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.webhooks.models import EmailEvent


class TestConversationsAPI(APITestCase):
    def setUp(self):
        self.participant1 = UserFactory()
        self.participant2 = UserFactory()
        self.participant3 = UserFactory()
        self.not_participant1 = UserFactory()
        self.not_participant2 = UserFactory()
        self.not_participant3 = UserFactory()
        self.conversation1 = ConversationFactory()
        self.conversation1.sync_users([
            self.participant1, self.participant2, self.participant3
        ])
        self.conversation1.messages.create(author=self.participant1, content='hello')
        self.conversation2 = ConversationFactory()
        self.conversation2.sync_users([
            self.participant1
        ])
        self.conversation2.messages.create(author=self.participant1, content='hello2')
        self.conversation3 = ConversationFactory()  # conversation noone is in

    def test_get_messages(self):
        self.client.force_login(user=self.participant1)
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
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_same_error_if_conversation_does_not_exist_as_if_you_are_just_not_in_it(self):
        self.client.force_login(user=self.participant1)
        response = self.client.get('/api/messages/?conversation={}'.format(982398723), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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


class TestConversationThreadsAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.conversation = self.group.conversation
        self.thread = self.conversation.messages.create(author=self.user, content='yay')

    def create_reply(self, **kwargs):
        return ConversationMessage.objects.create(
            conversation=self.conversation,
            author=self.user,
            thread=self.thread,
            content='default reply',
            **kwargs,
        )

    def test_thread_reply(self):
        self.client.force_login(user=self.user)
        data = {'conversation': self.conversation.id, 'content': 'a nice message reply!', 'thread': self.thread.id}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['thread'], self.thread.id)

    def test_returns_thread_and_replies(self):
        self.client.force_login(user=self.user)
        another_thread = self.conversation.messages.create(author=self.user, content='my own thread')
        n = 5
        [ConversationMessage.objects.create(
            conversation=self.conversation,
            author=self.user,
            thread=another_thread,
            content='default reply',
        ) for _ in range(n)]
        response = self.client.get('/api/messages/?thread={}'.format(another_thread.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), n + 1)

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
        reply = self.create_reply()
        data = {'seen_up_to': reply.id}
        response = self.client.patch('/api/messages/{}/thread/'.format(self.thread.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        participant = self.thread.participants.get(user=self.user)
        self.assertEqual(participant.seen_up_to, reply)

    def test_cannot_mute_thread_with_no_replies(self):
        self.client.force_login(user=self.user)
        another_message = self.conversation.messages.create(author=self.user, content='boo')
        data = {'muted': True}
        response = self.client.patch('/api/messages/{}/thread/'.format(another_message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_thread_meta_for_particiant(self):
        self.client.force_login(user=self.user)
        reply = self.create_reply()
        response = self.client.get('/api/messages/', format='json')
        item = response.data['results'][0]
        self.assertEqual(item['thread'], self.thread.id)
        self.assertEqual(item['thread_meta'], {
            'is_participant': True,
            'participants': [self.user.id],
            'reply_count': 1,
            'seen_up_to': reply.id,
            'muted': False,
            'unread_reply_count': 0,
        })

    def test_get_thread_meta_for_non_participant(self):
        self.client.force_login(user=self.user2)
        self.create_reply()
        response = self.client.get('/api/messages/', format='json')
        item = response.data['results'][0]
        self.assertEqual(item['thread'], self.thread.id)
        self.assertEqual(item['thread_meta'], {
            'is_participant': False,
            'participants': [self.user.id],
            'reply_count': 1,
        })

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

        response = self.client.get('/api/conversations/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['seen_up_to'], message.id)

    def test_mark_seen_up_to(self):
        message = self.conversation.messages.create(author=self.user2, content='yay')
        self.client.force_login(user=self.user)

        response = self.client.get('/api/conversations/{}/'.format(self.conversation.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], None)

        data = {'seen_up_to': message.id}
        response = self.client.post('/api/conversations/{}/mark/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['seen_up_to'], message.id)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.seen_up_to, message)

    def test_mark_seen_up_to_fails_for_invalid_id(self):
        self.client.force_login(user=self.user)
        data = {'seen_up_to': 9817298172}
        response = self.client.post('/api/conversations/{}/mark/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['seen_up_to'][0],
                         'Invalid pk "{}" - object does not exist.'.format(data['seen_up_to']))

    def test_mark_seen_up_to_fails_for_message_in_other_conversation(self):
        conversation = ConversationFactory(participants=[self.user, ])

        message = conversation.messages.create(author=self.user, content='yay')
        self.client.force_login(user=self.user)

        data = {'seen_up_to': message.id}
        response = self.client.post('/api/conversations/{}/mark/'.format(self.conversation.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['seen_up_to'][0], 'Must refer to a message in the conversation')


class TestConversationsEmailNotificationsAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user])
        self.conversation = self.group.conversation
        self.participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)

    def test_disable_email_notifications(self):
        participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.assertTrue(participant.email_notifications)

        self.client.force_login(user=self.user)

        data = {'email_notifications': False}
        response = self.client.post(
            '/api/conversations/{}/email_notifications/'.format(self.conversation.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email_notifications'], False)

        participant.refresh_from_db()
        self.assertFalse(participant.email_notifications)

    def test_enable_email_notifications(self):
        participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        participant.email_notifications = False
        participant.save()
        self.assertFalse(participant.email_notifications)

        self.client.force_login(user=self.user)

        data = {'email_notifications': True}
        response = self.client.post(
            '/api/conversations/{}/email_notifications/'.format(self.conversation.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email_notifications'], True)

        participant.refresh_from_db()
        self.assertTrue(participant.email_notifications)

    def test_send_email_notifications(self):
        users = [VerifiedUserFactory() for _ in range(3)]
        [self.group.add_member(u) for u in users]

        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')

        actual_recipients = set(m.to[0] for m in mail.outbox)
        expected_recipients = set(u.email for u in users)

        self.assertEqual(actual_recipients, expected_recipients)

        self.assertEqual(len(mail.outbox), 3)

    def test_exclude_bounced_addresses(self):
        bounce_user = VerifiedUserFactory()
        self.group.add_member(bounce_user)
        for _ in range(5):
            EmailEvent.objects.create(address=bounce_user.email, event='bounce', payload={})

        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')
        self.assertEqual(len(mail.outbox), 0)

    def test_not_exclude_bounced_addresses_if_too_old(self):
        bounce_user = VerifiedUserFactory()
        self.group.add_member(bounce_user)

        some_months_ago = timezone.now() - relativedelta(months=4)
        for _ in range(5):
            EmailEvent.objects.create(created_at=some_months_ago, address=bounce_user.email, event='bounce', payload={})

        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')
        self.assertEqual(len(mail.outbox), 1)

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
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_emoji_to_message_of_other_group(self):
        """It should be impossible to add emoji to a message from group user is not member of."""

        # log in as user who didn't join the conversation
        self.client.force_login(user=self.user2)
        data = {'name': 'thumbsup'}
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message2.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_to_message_with_invalid_id(self):
        """It should fail predictably when message has invalid id. (respond status 404)"""
        self.client.force_login(user=self.user)
        data = {'name': 'thumbsup'}
        response = self.client.post(
            '/api/messages/{}/reactions/'.format('invalid'),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_nonexistent_emoji(self):
        """It should be impossible to add an unsupported emoji. (respond 400)"""
        self.client.force_login(user=self.user)
        data = {'name': 'nonexistent_emoji'}
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_request_fails(self):
        """If no emoji is given, the request should fail (respond 400)"""
        self.client.force_login(user=self.user)
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reaction_to_nonexistent_message(self):
        """It should error with 404 when trying to react to nonexistent message."""

        # log in as user who didn't join the conversation
        self.client.force_login(user=self.user)

        data = {'name': 'thumbsup'}
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(1735),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_dont_react_twice_with_the_same_emoji(self):
        """Can not react with the same emoji twice."""
        self.client.force_login(user=self.user)
        data = {'name': 'thumbsup'}

        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_react_to_message_with_emoji(self):
        """User who can participate in conversation can react to a message with emoji."""
        self.client.force_login(user=self.user)
        data = {'name': 'tada'}
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
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
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'thumbsup')

        # and the base form can't be saved now
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            {'name': 'thumbsup'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_react_with_different_emoji(self):
        """Can react multiple times with different emoji."""
        self.client.force_login(user=self.user)

        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            {'name': 'thumbsup'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # second request with different emoji is ok
        response = self.client.post(
            '/api/messages/{}/reactions/'.format(self.message.id),
            {'name': 'tada'},
            format='json'
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
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_not_in_conversation_cant_remove_reaction(self):
        """User can't remove a reaction of message from alien conversation, but fails with 403."""
        self.client.force_login(user=self.user2)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_reaction_invalid_message_id(self):
        """When message has invalid name, it should fail predictably. (404)"""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format('hello', 'thumbsup'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_reaction_invalid_emoji_name(self):
        """When emoji has invalid name, response should be 400."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'invalid_emoji'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_reaction_message_not_exist(self):
        """When message with given id doesn't exist, respond with 404."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(7321, 'thumbsup'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_nonexisting_reaction(self):
        """When we try to remove nonexisting reaction, response should be 404."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, '-1'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_existing_reaction(self):
        """User can remove her reaction."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, 'thumbsup'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_remove_non_base_name(self):
        """Can remove +1, -1, which removes thumbsup, thumbsdown, etc."""
        self.client.force_login(user=self.user)

        response = self.client.delete(
            '/api/messages/{}/reactions/{}/'.format(self.message.id, '+1'),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TestConversationsMessageEditPatchAPI(APITestCase):
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
            author=self.user, content='hello3',
            created_at=(timezone.now() - timedelta(days=10)),
        )

    def test_update_message(self):
        self.client.force_login(user=self.user)
        data = {'content': 'hi'}
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cannot_update_message_without_specifying_content(self):
        self.client.force_login(user=self.user)
        data = {'content': ''}
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_update_message_if_not_in_conversation(self):
        self.client.force_login(user=self.user2)
        data = {'content': 'a nice message'}
        response = self.client.patch('/api/messages/{}/'.format(self.message.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Even if the participant is in the conversation,
    # they cannot edit messages they did not create.
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
