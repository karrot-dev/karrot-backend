from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestCleanupConversationParticipantsMigration(TestMigrations):
    """ Testing our conversation participant cleanup migration

    It's a bit of a basic test, as it doesn't run all the code where
    the magic really happens. But it at least ensures it runs in a basic way :)
    """

    migrate_from = [
        ('users', '0027_fix_usernames'),
        ('groups', '0049_auto_20220930_1506'),
        ('conversations', '0042_conversationmessageattachment'),
    ]
    migrate_to = [
        ('groups', '0049_auto_20220930_1506'),
        ('conversations', '0043__cleanup_conversation_participants'),
    ]

    def setUpBeforeMigration(self):
        User = self.apps.get_model('users', 'User')
        Group = self.apps.get_model('groups', 'Group')
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        Conversation = self.apps.get_model('conversations', 'Conversation')
        ConversationMessage = self.apps.get_model('conversations', 'ConversationMessage')
        ConversationParticipant = self.apps.get_model('conversations', 'ConversationParticipant')
        ConversationThreadParticipant = self.apps.get_model('conversations', 'ConversationThreadParticipant')

        user = User.objects.create()
        group = Group.objects.create(name=faker.name())
        other_group = Group.objects.create(name=faker.name())

        for g in [group, other_group]:
            GroupMembership.objects.create(group=g, user=user)
            conversation = Conversation.objects.create(group=g)
            ConversationParticipant.objects.create(conversation=conversation, user=user)
            message = ConversationMessage.objects.create(conversation=conversation, content='hello', author=user)
            ConversationMessage.objects.create(conversation=conversation, content='reply', author=user, thread=message)
            ConversationThreadParticipant.objects.create(user=user, thread=message)

        self.assertEqual(ConversationParticipant.objects.count(), 2)
        self.assertEqual(ConversationThreadParticipant.objects.count(), 2)

        GroupMembership.objects.filter(group=group, user=user).delete()

        self.user_id = user.id
        self.group_id = group.id
        self.other_group_id = other_group.id

    def test_removes_participants(self):
        User = self.apps.get_model('users', 'User')
        Group = self.apps.get_model('groups', 'Group')
        ConversationParticipant = self.apps.get_model('conversations', 'ConversationParticipant')
        ConversationThreadParticipant = self.apps.get_model('conversations', 'ConversationThreadParticipant')

        user = User.objects.get(id=self.user_id)
        group = Group.objects.get(id=self.group_id)
        other_group = Group.objects.get(id=self.other_group_id)

        self.assertEqual(ConversationParticipant.objects.count(), 1)
        self.assertEqual(ConversationThreadParticipant.objects.count(), 1)

        self.assertFalse(ConversationParticipant.objects.filter(conversation__group=group, user=user).exists())
        self.assertFalse(
            ConversationThreadParticipant.objects.filter(thread__conversation__group=group, user=user).exists()
        )

        self.assertTrue(ConversationParticipant.objects.filter(conversation__group=other_group, user=user).exists())
        self.assertTrue(
            ConversationThreadParticipant.objects.filter(thread__conversation__group=other_group, user=user).exists()
        )
