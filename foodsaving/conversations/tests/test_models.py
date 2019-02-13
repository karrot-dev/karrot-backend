from django.core import mail
from django.db import IntegrityError
from django.test import TestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.conversations.models import Conversation, ConversationMessage, ConversationMessageReaction, \
    ConversationThreadParticipant, ConversationParticipant
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupNotificationType
from foodsaving.issues.factories import IssueFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.places.factories import PlaceFactory
from foodsaving.users.factories import UserFactory, VerifiedUserFactory


class ConversationModelTests(TestCase):
    def test_join(self):
        user = UserFactory()
        conversation = ConversationFactory(participants=[user])
        self.assertIn(user, conversation.participants.all())

    def test_leave(self):
        user = UserFactory()
        conversation = ConversationFactory(participants=[user])
        self.assertIn(user, conversation.participants.all())

        conversation.leave(user)
        self.assertNotIn(user, conversation.participants.all())

    def test_sync_users(self):
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()
        user4 = UserFactory()
        users = [user1, user2, user3]
        conversation = ConversationFactory()
        conversation.join(user1)  # should not be added again
        conversation.join(user4)  # should be removed
        conversation.sync_users(users)
        self.assertEqual(conversation.participants.count(), 3)
        self.assertIn(user1, conversation.participants.all())
        self.assertIn(user2, conversation.participants.all())
        self.assertIn(user3, conversation.participants.all())
        self.assertNotIn(user4, conversation.participants.all())

    def test_message_create(self):
        user = UserFactory()
        conversation = ConversationFactory(participants=[user])
        conversation.messages.create(author=user, content='yay')
        self.assertEqual(ConversationMessage.objects.filter(author=user).count(), 1)

    def test_keeps_latest_message_updated(self):
        user = UserFactory()
        conversation = ConversationFactory(participants=[user])
        message = conversation.messages.create(author=user, content='yay')
        self.assertEqual(conversation.latest_message, message)

        message = conversation.messages.create(author=user, content='yay2')
        self.assertEqual(conversation.latest_message, message)

    def test_message_create_requires_author(self):
        conversation = ConversationFactory()
        with self.assertRaises(IntegrityError):
            conversation.messages.create(content='ohno')

    def test_creating_from_target(self):
        target = GroupFactory()  # could be any model
        conversation = Conversation.objects.get_or_create_for_target(target)
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.target, target)

    def test_mixin(self):
        target = GroupFactory()  # must be a model which uses the mixin
        conversation = Conversation.objects.get_or_create_for_target(target)
        self.assertIsNotNone(conversation)
        self.assertEqual(target.conversation, conversation)


class ConversationThreadModelTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user2 = UserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.conversation = self.group.conversation
        self.thread = self.conversation.messages.create(author=self.user, content='yay')

    def create_reply(self, **kwargs):
        args = {
            'conversation': self.conversation,
            'author': self.user,
            'thread': self.thread,
            'content': 'my reply',
        }
        args.update(kwargs)
        return ConversationMessage.objects.create(**args)

    def test_keeps_latest_message_updated(self):
        message = self.create_reply()
        self.assertEqual(self.thread.latest_message, message)

        message = self.create_reply()
        self.assertEqual(self.thread.latest_message, message)

    def test_replies_count_annotation(self):
        self.thread.participants.create(user=self.user2)
        n = 4
        [self.create_reply() for _ in range(n)]

        message = ConversationMessage.objects \
            .annotate_replies_count() \
            .get(pk=self.thread.id)

        self.assertEqual(message.replies_count, n)
        self.assertEqual(message._replies_count, n)

    def test_unread_replies_count_annotation(self):
        self.thread.participants.create(user=self.user2)
        n = 7
        read_messages = 2
        messages = [self.create_reply() for _ in range(n)]

        # "read" some of the messages
        ConversationThreadParticipant.objects \
            .filter(user=self.user2, thread=self.thread.id) \
            .update(seen_up_to=messages[read_messages - 1])

        message = ConversationMessage.objects \
            .annotate_unread_replies_count_for(self.user2) \
            .get(pk=self.thread.id)

        self.assertEqual(message.unread_replies_count, n - read_messages)

    def test_unread_message_count_annotation_does_not_include_replies(self):
        self.thread.participants.create(user=self.user2)
        self.create_reply()

        participant = ConversationParticipant.objects \
            .annotate_unread_message_count() \
            .get(conversation=self.conversation, user=self.user2)

        self.assertEqual(participant.unread_message_count, 1)

    def test_default_replies_count_property(self):
        self.assertEqual(self.thread.replies_count, 0)
        n = 5
        [self.create_reply() for _ in range(n)]
        self.assertEqual(self.thread.replies_count, n)

    def test_annotation_replies_count_property(self):
        self.thread = ConversationMessage.objects \
            .annotate_replies_count() \
            .get(pk=self.thread.id)
        self.assertEqual(self.thread.replies_count, 0)
        n = 5
        [self.create_reply() for _ in range(n)]
        self.assertEqual(self.thread.replies_count, n)


class TestPlaceConversations(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.place = PlaceFactory(subscribers=[self.user, self.user2])
        self.conversation = self.place.conversation
        mail.outbox = []

    def test_message_email_notifications(self):
        message = self.conversation.messages.create(author=self.user, content='asdf')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.place.name, mail.outbox[0].subject)
        self.assertIn(message.content, mail.outbox[0].body)

    def test_reply_email_notifications(self):
        message = self.conversation.messages.create(author=self.user, content='asdf')
        mail.outbox = []
        reply = self.conversation.messages.create(author=self.user2, thread=message, content='my reply')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(message.content, mail.outbox[0].subject)
        self.assertIn(reply.content, mail.outbox[0].body)


class TestPickupConversations(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place, collectors=[self.user])
        self.conversation = self.pickup.conversation

    def test_send_email_notifications(self):
        users = [VerifiedUserFactory() for _ in range(2)]
        [self.pickup.add_collector(u) for u in users]

        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')

        actual_recipients = sorted(m.to[0] for m in mail.outbox)
        expected_recipients = sorted(u.email for u in users)

        self.assertEqual(actual_recipients, expected_recipients)

        self.assertEqual(len(mail.outbox), 2)


class TestIssueConversations(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.more_users = [VerifiedUserFactory() for _ in range(2)]
        self.group = GroupFactory(members=[self.user, *self.more_users])
        for membership in self.group.groupmembership_set.all():
            membership.add_notification_types([GroupNotificationType.CONFLICT_RESOLUTION])
            membership.save()
        self.issue = IssueFactory(group=self.group, created_by=self.user)
        self.conversation = self.issue.conversation
        mail.outbox = []

    def test_send_email_notifications(self):
        ConversationMessage.objects.create(author=self.user, conversation=self.conversation, content='asdf')

        self.assertEqual(len(mail.outbox), 2)

        actual_recipients = set(m.to[0] for m in mail.outbox)
        expected_recipients = set(u.email for u in self.more_users)

        self.assertEqual(actual_recipients, expected_recipients)


class TestPrivateUserConversations(TestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()

    def test_send_email_notifications(self):
        conversation = Conversation.objects.get_or_create_for_two_users(self.user, self.user2)
        mail.outbox = []
        ConversationMessage.objects.create(author=self.user, conversation=conversation, content='asdf')

        self.assertEqual(len(mail.outbox), 1)

        actual_recipient = mail.outbox[0].to[0]
        expected_recipient = self.user2.email
        self.assertEqual(actual_recipient, expected_recipient)

        self.assertEqual(len(mail.outbox), 1)

    def test_get_or_create_conversation(self):
        new_user = UserFactory()
        c = Conversation.objects.get_or_create_for_two_users(self.user, new_user)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(c.participants.count(), 2)
        self.assertIn(self.user, c.participants.all())
        self.assertIn(new_user, c.participants.all())
        conversation_id = c.id

        c = Conversation.objects.get_or_create_for_two_users(self.user, new_user)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(c.participants.count(), 2)
        self.assertEqual(conversation_id, c.id)
        self.assertEqual(c.type(), 'private')

    def test_get_or_create_conversation_for_yourself_fails(self):
        with self.assertRaises(Exception):
            Conversation.objects.get_or_create_for_two_users(self.user, self.user)

    def test_does_not_set_group(self):
        conversation = Conversation.objects.get_or_create_for_two_users(self.user, self.user2)
        self.assertIsNone(conversation.group)


class TestGroupConversation(TestCase):
    def test_sets_group(self):
        user = VerifiedUserFactory()
        group = GroupFactory(members=[user])
        conversation = Conversation.objects.get_or_create_for_target(group)
        self.assertEqual(conversation.group, group)


class ReactionModelTests(TestCase):
    def test_reaction_create(self):
        user = UserFactory()
        conversation = ConversationFactory()
        conversation.sync_users([user])
        message = conversation.messages.create(author=user, content='hello')
        message.reactions.create(message=message, user=user, name='tada')
        self.assertEqual(ConversationMessageReaction.objects.filter(message=message, user=user).count(), 1)

    def test_reaction_remove(self):
        # setup
        user = UserFactory()
        conversation = ConversationFactory()
        conversation.sync_users([user])
        message = conversation.messages.create(author=user, content='hello')
        # creating reaction
        message.reactions.create(message=message, user=user, name='tada')
        instance = ConversationMessageReaction.objects.get(message=message, user=user, name='tada')
        # remove reaction
        instance.delete()
        self.assertEqual(ConversationMessageReaction.objects.filter(message=message, user=user).count(), 0)
