from foodsaving.tests.utils import TestMigrations
from foodsaving.utils.tests.fake import faker


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
