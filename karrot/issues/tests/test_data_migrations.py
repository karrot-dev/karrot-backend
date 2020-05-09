from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestEnableIssueNotifications(TestMigrations):
    migrate_from = [
        ('groups', '0042_auto_20200507_1258'),
        ('users', '0022_auto_20190404_1919'),
        ('issues', '0003_issue_status_changed_at'),
    ]
    migrate_to = [
        ('issues', '0004_enable_issue_notifications'),
    ]

    def setUpBeforeMigration(self, apps):
        Group = apps.get_model('groups', 'Group')
        GroupMembership = apps.get_model('groups', 'GroupMembership')
        User = apps.get_model('users', 'User')
        group = Group.objects.create(name=faker.name())
        user1 = User.objects.create()
        user2 = User.objects.create()
        membership1 = GroupMembership.objects.create(group=group, user=user1, notification_types=[])
        membership2 = GroupMembership.objects.create(
            group=group, user=user2, notification_types=['conflict_resolution', 'other', 'stuff']
        )
        self.assertEqual(membership1.notification_types, [])
        self.assertEqual(membership2.notification_types, ['conflict_resolution', 'other', 'stuff'])
        self.membership1_id = membership1.id
        self.membership2_id = membership2.id

    def test_enables_issue_notifications(self):
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        membership1 = GroupMembership.objects.get(pk=self.membership1_id)
        self.assertEqual(membership1.notification_types, ['conflict_resolution'])

    def test_keeps_other_notification_types(self):
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        membership2 = GroupMembership.objects.get(pk=self.membership2_id)
        self.assertEqual(membership2.notification_types, ['conflict_resolution', 'other', 'stuff'])
