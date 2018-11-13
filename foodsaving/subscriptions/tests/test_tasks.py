from datetime import datetime

from dateutil.parser import parse
from django.test import TestCase

from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.conversations.models import Conversation, ConversationMessage
from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.subscriptions.tasks import get_message_title
from foodsaving.users.factories import UserFactory


class TestMessagePushNotifications(TestCase):
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
        store = StoreFactory(group=group)
        pickup = PickupDateFactory(store=store, collectors=[author], date=parse('2018-11-11T20:00:00Z'))
        conversation = Conversation.objects.get_or_create_for_target(pickup)
        message = conversation.messages.create(author=author, content='bla')

        title = get_message_title(message, 'en')
        self.assertEqual(title, 'Pickup Sunday 9:00 PM / {}'.format(author.display_name))

    def test_application_message_title(self):
        author = UserFactory()
        group = GroupFactory(members=[author])
        applicant = UserFactory()
        application = GroupApplicationFactory(group=group, user=applicant)
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
