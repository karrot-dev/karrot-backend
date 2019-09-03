from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time
from unittest.mock import patch

from karrot.conversations import tasks
from karrot.conversations.models import ConversationParticipant, ConversationThreadParticipant, Conversation
from karrot.conversations.tasks import mark_conversations_as_closed
from karrot.groups.factories import GroupFactory
from karrot.issues.factories import IssueFactory
from karrot.tests.utils import execute_scheduled_tasks_immediately
from karrot.users.factories import VerifiedUserFactory, UserFactory


def suppressed_notifications():
    return patch('karrot.conversations.receivers.tasks.notify_participants')


class TestBatchedConversationNotificationTask(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.author = VerifiedUserFactory()
        self.conversation = Conversation.objects.get_or_create_for_two_users(self.author, self.user)
        with suppressed_notifications():
            self.message = self.conversation.messages.create(author=self.author, content='initial message')
        mail.outbox = []

    def test_skip_task_if_more_recent_message_exists(self):
        with suppressed_notifications():
            self.conversation.messages.create(author=self.author, content='foo')

        tasks.notify_participants(self.message)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_notification_batching(self):
        with execute_scheduled_tasks_immediately():
            recent_message = self.conversation.messages.create(author=self.author, content='first reply')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(recent_message.content, mail.outbox[0].body)

        # and another three messages, to check if notified_up_to is updated
        mail.outbox = []
        with suppressed_notifications():
            two = self.conversation.messages.create(author=self.author, content='second message')
            self.conversation.messages.create(author=self.author, content='three')
        self.conversation.conversationparticipant_set.filter(user=self.user).update(seen_up_to=two)
        with execute_scheduled_tasks_immediately():
            recent_message = self.conversation.messages.create(author=self.author, content='four')

        self.assertEqual(len(mail.outbox), 1)
        user1_email = next(email for email in mail.outbox if email.to[0] == self.user.email)
        self.assertNotIn('second message', user1_email.body)
        self.assertIn('three', user1_email.body)
        self.assertIn('four', user1_email.body)
        self.assertIn(self.author.display_name, mail.outbox[0].from_email)
        participant = ConversationParticipant.objects.get(conversation=self.conversation, user=self.user)
        self.assertEqual(participant.notified_up_to.id, recent_message.id)


class TestConversationNotificationTask(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.author = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.author, self.user])
        mail.outbox = []
        with suppressed_notifications():
            self.message = self.group.conversation.messages.create(author=self.author, content='initial message')

    def test_only_notifies_active_group_members(self):
        self.group.add_member(UserFactory())
        inactive_user = VerifiedUserFactory()
        self.group.add_member(inactive_user)
        self.group.groupmembership_set.filter(user=inactive_user).update(inactive_at=timezone.now())
        mail.outbox = []
        with execute_scheduled_tasks_immediately():
            self.group.conversation.messages.create(author=self.author, content='foo')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_notify_about_unseen_message(self):
        self.group.conversation.conversationparticipant_set.filter(user=self.user).update(seen_up_to=self.message)
        with execute_scheduled_tasks_immediately():
            self.group.conversation.messages.create(author=self.author, content='this should be sent')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.user.email)
        self.assertIn('this should be sent', mail.outbox[0].body)
        self.assertNotIn('initial message', mail.outbox[0].body)

    def test_exclude_seen_message(self):
        with suppressed_notifications():
            another_message = self.group.conversation.messages.create(author=self.author, content='foo')
        self.group.conversation.conversationparticipant_set.filter(user=self.user).update(seen_up_to=another_message)

        tasks.notify_participants(another_message)
        self.assertEqual(len(mail.outbox), 0)

    def test_exclude_thread_replies_from_conversation_notification(self):
        with suppressed_notifications():
            self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='first thread reply'
            )
        with execute_scheduled_tasks_immediately():
            self.group.conversation.messages.create(author=self.author, content='conversation')

        self.assertNotIn('first thread reply', mail.outbox[0].body)

    def test_does_notification_batching_in_threads(self):
        with suppressed_notifications():
            self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='first thread reply'
            )
        with execute_scheduled_tasks_immediately():
            recent_message = self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='second thread reply'
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('first thread reply', mail.outbox[0].body)
        self.assertIn('second thread reply', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to[0], self.author.email)
        participant = ConversationThreadParticipant.objects.get(thread=self.message, user=self.author)
        self.assertEqual(participant.notified_up_to.id, recent_message.id)

    def test_exclude_seen_message_in_thread(self):
        with suppressed_notifications():
            another_message = self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='first thread reply'
            )
        ConversationThreadParticipant.objects.filter(
            thread=self.message, user=self.author
        ).update(seen_up_to=another_message)

        self.assertEqual(len(mail.outbox), 0)

    def test_exclude_already_notified_in_thread(self):
        with execute_scheduled_tasks_immediately():
            self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='first thread reply'
            )
            mail.outbox = []
            self.group.conversation.messages.create(
                author=self.user, thread=self.message, content='second thread reply'
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('second thread reply', mail.outbox[0].body)
        self.assertNotIn('first thread reply', mail.outbox[0].body)


class TestMarkConversationClosedTask(TestCase):
    def test_mark_issue_conversation_as_closed(self):
        long_time_ago = timezone.now() - relativedelta(days=30)

        # not cancelled -> should stay open
        issue = IssueFactory()
        conversation = issue.conversation
        conversation.messages.create(content='hello', author=issue.created_by, created_at=long_time_ago)

        # cancelled but recently commented on -> should stay open
        with freeze_time(long_time_ago, tick=True):
            issue_ended_recently = IssueFactory()
            issue_ended_recently.cancel()
        conversation_ended_recently = issue_ended_recently.conversation
        conversation_ended_recently.messages.create(
            content='hello', author=issue_ended_recently.created_by, created_at=timezone.now()
        )

        # cancelled and not commented on -> should be closed
        with freeze_time(long_time_ago, tick=True):
            issue_ended = IssueFactory()
            issue_ended.cancel()
        conversation_ended = issue_ended.conversation
        conversation_ended.messages.create(content='hello', author=issue_ended.created_by, created_at=long_time_ago)

        conversations = Conversation.objects.filter(target_type__model='issue')
        self.assertEqual(conversations.count(), 3)
        self.assertEqual(conversations.filter(is_closed=False).count(), 3)

        mark_conversations_as_closed()

        self.assertEqual(conversations.filter(is_closed=False).count(), 2)
        self.assertEqual(conversations.filter(is_closed=True).first(), conversation_ended)

    def test_mark_empty_as_closed(self):
        long_time_ago = timezone.now() - relativedelta(days=30)

        # no messages and cancelled some time ago -> should be closed
        with freeze_time(long_time_ago, tick=True):
            issue_ended_long_ago = IssueFactory()
            issue_ended_long_ago.cancel()

        # no messages and cancelled recently -> should stay open
        issue_ended_recently = IssueFactory()
        issue_ended_recently.cancel()

        mark_conversations_as_closed()

        conversations = Conversation.objects.filter(target_type__model='issue')
        self.assertEqual(conversations.filter(is_closed=True).first(), issue_ended_long_ago.conversation)
        self.assertEqual(conversations.filter(is_closed=False).first(), issue_ended_recently.conversation)
