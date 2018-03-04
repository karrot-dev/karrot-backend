from foodsaving.groups.roles import GROUP_APPROVED_MEMBER
from foodsaving.tests.utils import TestMigrations


class TestMembershipsGetApprovedRole(TestMigrations):
    migrate_from = [('groups', '0021_groupmembership_notification_types'),
                    ('users', '0019_remove_verification_codes')]
    migrate_to = [('groups', '0022_groupmembership_approve_all'),
                  ('users', '0019_remove_verification_codes')]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        GroupMembership = apps.get_model('groups', 'GroupMembership')

        user = User.objects.create()
        group = Group.objects.create()
        GroupMembership.objects.create(user = user, group = group)

    def test_extract_pickups_from_stores_app(self):
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        self.assertIn(GROUP_APPROVED_MEMBER, GroupMembership.objects.first().roles)
