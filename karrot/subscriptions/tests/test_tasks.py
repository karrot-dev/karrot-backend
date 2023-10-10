from unittest.mock import patch, call

from dateutil.parser import parse
from django.db.models.signals import post_save
from django.test import TestCase
from factory.django import mute_signals

from karrot.applications.factories import ApplicationFactory
from karrot.issues.factories import IssueFactory
from karrot.conversations.models import Conversation, ConversationMessage, ConversationThreadParticipant, \
    ConversationParticipant
from karrot.groups.factories import GroupFactory
from karrot.activities.factories import ActivityFactory
from karrot.activities.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.subscriptions.factories import WebPushSubscriptionFactory
from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.tasks import get_message_title, notify_message_push_subscribers
from karrot.users.factories import UserFactory


@patch('karrot.subscriptions.tasks.notify_message_push_subscribers_with_language')
class TestMessagePushNotifications(TestCase):
    def test_message_notification(self, notify):
        author = UserFactory()
        user = UserFactory()
        group = GroupFactory(members=[author, user])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        with mute_signals(post_save):
            subscriptions = [WebPushSubscriptionFactory(user=user)]

        notify.reset_mock()
        notify_message_push_subscribers(message)
        notify.assert_called_once_with(message, subscriptions, 'en')

    def test_reply_notification(self, notify):
        author = UserFactory()
        reply_author = UserFactory()
        group = GroupFactory(members=[author, reply_author])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')
        reply = ConversationMessage.objects.create(
            author=reply_author, conversation=conversation, thread=message, content='reply'
        )
        with mute_signals(post_save):
            subscriptions = [WebPushSubscriptionFactory(user=author)]

        notify.reset_mock()
        notify_message_push_subscribers(reply)
        notify.assert_called_once_with(reply, subscriptions, 'en')

    def test_groups_by_language(self, notify):
        author = UserFactory()
        users = [UserFactory(language=language) for language in ('de', 'de', 'en', 'fr')]
        group = GroupFactory(members=[author, *users])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        with mute_signals(post_save):
            subscriptions = [WebPushSubscriptionFactory(user=u) for u in users]

        notify.reset_mock()
        notify_message_push_subscribers(message)
        notify.assert_has_calls([
            call(message, subscriptions[:2], 'de'),
            call(message, subscriptions[2:3], 'en'),
            call(message, subscriptions[3:4], 'fr'),
        ])
        self.assertEqual(len(notify.call_args_list), 3)

    def test_no_message_notification_if_muted(self, notify):
        author = UserFactory()
        user = UserFactory()
        group = GroupFactory(members=[author, user])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        participant = ConversationParticipant.objects.get(user=user, conversation=conversation)
        participant.muted = True
        participant.save()
        with mute_signals(post_save):
            WebPushSubscriptionFactory(user=user)

        notify.reset_mock()
        notify_message_push_subscribers(message)
        notify.assert_not_called()

    def test_no_reply_notification_if_muted(self, notify):
        author = UserFactory()
        reply_author = UserFactory()
        group = GroupFactory(members=[author, reply_author])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')
        reply = ConversationMessage.objects.create(
            author=reply_author, conversation=conversation, thread=message, content='reply'
        )

        participant = ConversationThreadParticipant.objects.get(user=author, thread=reply.thread)
        participant.muted = True
        participant.save()
        with mute_signals(post_save):
            WebPushSubscription(user=author)

        notify.reset_mock()
        notify_message_push_subscribers(reply)
        notify.assert_not_called()


class TestMessagePushNotificationTitles(TestCase):
    def test_private_message_title(self):
        author = UserFactory()
        user = UserFactory()
        conversation = Conversation.objects.get_or_create_for_two_users(author, user)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, author.display_name)

    def test_group_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, '{} / {}'.format(group.name, author.display_name))

    def test_place_message_title(self):
        author = UserFactory()
        place = PlaceFactory()
        conversation = Conversation.objects.get_or_create_for_target(place)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, '{} / {}'.format(place.name, author.display_name))

    def test_reply_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla' * 10)
        reply = ConversationMessage.objects.create(
            author=author, conversation=conversation, thread=message, content='reply'
        )

        title = get_message_title(reply, 'en')
        self.assertEqual(title, 'blablablablabl… / {}'.format(author.display_name))

    def test_activity_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author], timezone='Europe/Berlin')
        place = PlaceFactory(group=group)
        activity = ActivityFactory(place=place, participants=[author], date=to_range(parse('2018-11-11T20:00:00Z')))
        conversation = Conversation.objects.get_or_create_for_target(activity)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(
            title, '{} Sunday 9:00 PM / {}'.format(activity.activity_type.get_translated_name(), author.display_name)
        )

    def test_application_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author])
        applicant = UserFactory()
        application = ApplicationFactory(group=group, user=applicant)
        conversation = Conversation.objects.get_or_create_for_target(application)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, '❓ {} / {}'.format(applicant.display_name, author.display_name))

        application.accept(author)
        message.refresh_from_db()
        title = get_message_title(message, 'en')
        self.assertEqual(title, '✅ {} / {}'.format(applicant.display_name, author.display_name))

        application.decline(author)
        message.refresh_from_db()
        title = get_message_title(message, 'en')
        self.assertEqual(title, '❌ {} / {}'.format(applicant.display_name, author.display_name))

        application.withdraw()
        message.refresh_from_db()
        title = get_message_title(message, 'en')
        self.assertEqual(title, '🗑️ {} / {}'.format(applicant.display_name, author.display_name))

        message = conversation.messages.create(author=applicant, content='bla')
        message.refresh_from_db()
        title = get_message_title(message, 'en')
        self.assertEqual(title, '🗑️ {}'.format(applicant.display_name))

    def test_issue_message_title(self):
        issue = IssueFactory()
        author = issue.group.members.first()
        conversation = issue.conversation
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertIn('☹️', title)
