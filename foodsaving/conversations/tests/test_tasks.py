from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from foodsaving.conversations import tasks
from foodsaving.conversations.models import ConversationParticipant, ConversationThreadParticipant
from foodsaving.groups.factories import GroupFactory
from foodsaving.users.factories import VerifiedUserFactory, UserFactory


class TestConversationNotificationTask(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.author = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.author, self.user])
        mail.outbox = []
        with patch('foodsaving.conversations.receivers.tasks.notify_participants'):
            self.message = self.group.conversation.messages.create(author=self.author, content='initial message')

    def test_only_notifies_active_group_members(self):
        self.group.add_member(UserFactory())
        inactive_user = VerifiedUserFactory()
        self.group.add_member(inactive_user)
        self.group.groupmembership_set.filter(user=inactive_user).update(inactive_at=timezone.now())
        mail.outbox = []
        self.group.conversation.messages.create(author=self.author, content='foo')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_notify_about_unseen_message(self):
        self.group.conversation.conversationparticipant_set.filter(user=self.user).update(seen_up_to=self.message)
        self.group.conversation.messages.create(author=self.author, content='this should be sent')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.user.email)
        self.assertIn('this should be sent', mail.outbox[0].body)
        self.assertNotIn('initial message', mail.outbox[0].body)

    def test_exclude_seen_message(self):
        with patch('foodsaving.conversations.receivers.tasks.notify_participants'):
            another_message = self.group.conversation.messages.create(author=self.author, content='foo')
        self.group.conversation.conversationparticipant_set.filter(user=self.user).update(seen_up_to=another_message)

        tasks.notify_participants(another_message)
        self.assertEqual(len(mail.outbox), 0)

    def test_skip_task_if_more_recent_message_exists(self):
        with patch('foodsaving.conversations.receivers.tasks.notify_participants'):
            self.group.conversation.messages.create(author=self.author, content='foo')

        tasks.notify_participants(self.message)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_notification_batching(self):
        recent_message = self.group.conversation.messages.create(author=self.author, content='first reply')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(recent_message.content, mail.outbox[0].body)
        self.assertIn(self.message.content, mail.outbox[0].body)

        # and another three messages, to check if notified_up_to is updated
        mail.outbox = []
        with patch('foodsaving.conversations.receivers.tasks.notify_participants'):
            self.group.conversation.messages.create(author=self.author, content='two')
            self.group.conversation.messages.create(author=self.author, content='three')
        recent_message = self.group.conversation.messages.create(author=self.author, content='four')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('two', mail.outbox[0].body)
        self.assertIn('three', mail.outbox[0].body)
        self.assertIn('four', mail.outbox[0].body)
        self.assertIn(self.author.display_name, mail.outbox[0].from_email)
        participant = ConversationParticipant.objects.get(conversation=self.group.conversation, user=self.user)
        self.assertEqual(participant.notified_up_to.id, recent_message.id)

    def test_does_notification_batching_in_threads(self):
        with patch('foodsaving.conversations.receivers.tasks.notify_participants'):
            self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='first thread reply'
            )
        recent_message = self.group.conversation.messages.create(
            author=self.user, thread=self.message, content='second thread reply'
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('first thread reply', mail.outbox[0].body)
        self.assertIn('second thread reply', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to[0], self.author.email)
        participant = ConversationThreadParticipant.objects.get(thread=self.message, user=self.author)
        self.assertEqual(participant.notified_up_to.id, recent_message.id)
