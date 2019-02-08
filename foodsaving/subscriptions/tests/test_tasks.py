from unittest.mock import patch, call

from dateutil.parser import parse
from django.test import TestCase

from foodsaving.applications.factories import ApplicationFactory
from foodsaving.issues.factories import IssueFactory
from foodsaving.conversations.models import Conversation, ConversationMessage, ConversationThreadParticipant, \
    ConversationParticipant
from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.pickups.models import to_range
from foodsaving.places.factories import PlaceFactory
from foodsaving.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from foodsaving.subscriptions.tasks import get_message_title, notify_message_push_subscribers
from foodsaving.users.factories import UserFactory


@patch('foodsaving.subscriptions.tasks.notify_message_push_subscribers_with_language')
class TestMessagePushNotifications(TestCase):
    def test_message_notification(self, notify):
        author = UserFactory()
        user = UserFactory()
        group = GroupFactory(members=[author, user])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        subscriptions = [
            PushSubscription.objects.create(user=user, token='', platform=PushSubscriptionPlatform.ANDROID.value)
        ]

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
        subscriptions = [
            PushSubscription.objects.create(user=author, token='', platform=PushSubscriptionPlatform.ANDROID.value)
        ]

        notify.reset_mock()
        notify_message_push_subscribers(reply)
        notify.assert_called_once_with(reply, subscriptions, 'en')

    def test_groups_by_language(self, notify):
        author = UserFactory()
        users = [UserFactory(language=l) for l in ('de', 'de', 'en', 'fr')]
        group = GroupFactory(members=[author, *users])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla')

        subscriptions = [
            PushSubscription.objects.create(user=u, token='', platform=PushSubscriptionPlatform.ANDROID.value)
            for u in users
        ]

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
        PushSubscription.objects.create(user=user, token='', platform=PushSubscriptionPlatform.ANDROID.value)

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
        PushSubscription.objects.create(user=author, token='', platform=PushSubscriptionPlatform.ANDROID.value)

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

    def test_reply_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author])
        conversation = Conversation.objects.get_or_create_for_target(group)
        message = conversation.messages.create(author=author, content='bla' * 10)
        reply = ConversationMessage.objects.create(
            author=author, conversation=conversation, thread=message, content='reply'
        )

        title = get_message_title(reply, 'en')
        self.assertEqual(title, 'blablablabla... / {}'.format(author.display_name))

    def test_pickup_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author], timezone='Europe/Berlin')
        place = PlaceFactory(group=group)
        pickup = PickupDateFactory(place=place, collectors=[author], date=to_range(parse('2018-11-11T20:00:00Z')))
        conversation = Conversation.objects.get_or_create_for_target(pickup)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, 'Pickup Sunday 9:00 PM / {}'.format(author.display_name))

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
        author = issue.participants.first()
        conversation = issue.conversation
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertIn('💣', title)
