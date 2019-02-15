from django.utils import timezone

from karrot.pickups.models import to_range
from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestEmailNotificationSettingMigration(TestMigrations):
    migrate_from = [
        ('conversations', '0023_conversationparticipant_muted'),
        ('users', '0021_user_email_deletable'),
    ]
    migrate_to = [
        ('conversations', '0024_auto_20190107_0715'),
    ]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        Conversation = apps.get_model('conversations', 'Conversation')
        ConversationParticipant = apps.get_model('conversations', 'ConversationParticipant')

        user = User.objects.create(email=faker.email(), display_name=faker.name())
        conversation = Conversation.objects.create()
        self.non_muted_id = ConversationParticipant.objects.create(user=user, conversation=conversation).id

        conversation = Conversation.objects.create()
        self.muted_id = ConversationParticipant.objects.create(
            user=user, conversation=conversation, email_notifications=False
        ).id

    def test_migrates_email_notification_settings(self, *args):
        ConversationParticipant = self.apps.get_model('conversations', 'ConversationParticipant')

        self.assertFalse(ConversationParticipant.objects.get(id=self.non_muted_id).muted)
        self.assertTrue(ConversationParticipant.objects.get(id=self.muted_id).muted)


class TestConversationGroupMigration(TestMigrations):
    migrate_from = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('groups', '0036_group_photo'),
        ('places', '0031_auto_20181216_2133'),
        ('pickups', '0013_auto_20190122_1210'),
        ('applications', '0005_auto_20190125_1230'),
        ('conversations', '0028_auto_20190205_1558'),
    ]
    migrate_to = [
        ('conversations', '0029_set_conversation_group'),
    ]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        Place = apps.get_model('places', 'Place')
        Conversation = apps.get_model('conversations', 'Conversation')
        PickupDate = apps.get_model('pickups', 'PickupDate')
        Application = apps.get_model('applications', 'Application')
        ContentType = apps.get_model('contenttypes', 'ContentType')

        self.group = Group.objects.create(name='hello')
        target_type = ContentType.objects.get(app_label='groups', model='group')
        self.group_conversation = Conversation.objects.create(target_type=target_type, target_id=self.group.id)

        self.none_conversation = Conversation.objects.create()

        self.private_conversation = Conversation.objects.create(is_private=True)

        place = Place.objects.create(group=self.group)
        pickup = PickupDate.objects.create(place=place, date=to_range(timezone.now()))
        target_type = ContentType.objects.get(app_label='pickups', model='pickupdate')
        self.pickup_conversation = Conversation.objects.create(target_type=target_type, target_id=pickup.id)

        user = User.objects.create(email=faker.email())
        application = Application.objects.create(user=user, group=self.group)
        target_type = ContentType.objects.get(app_label='applications', model='application')
        self.application_conversation = Conversation.objects.create(target_type=target_type, target_id=application.id)

    def test_sets_conversation_group(self):
        self.group_conversation.refresh_from_db()
        self.pickup_conversation.refresh_from_db()
        self.application_conversation.refresh_from_db()

        self.assertIsNone(self.none_conversation.target_id)
        self.assertIsNone(self.private_conversation.target_id)
        self.assertEqual(self.group_conversation.group, self.group)
        self.assertEqual(self.pickup_conversation.group, self.group)
        self.assertEqual(self.application_conversation.group, self.group)
