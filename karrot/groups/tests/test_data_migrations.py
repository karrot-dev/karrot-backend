import datetime

from psycopg2.extras import DateTimeTZRange

from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


def to_range(date, **kwargs):
    duration = datetime.timedelta(**kwargs) if kwargs else datetime.timedelta(minutes=30)
    return DateTimeTZRange(date, date + duration)


class TestAddNewcomerRoleMigration(TestMigrations):
    migrate_from = [
        ('users', '0027_fix_usernames'),
        ('groups', '0046_groupmembership_must_have_member_role'),
    ]
    migrate_to = [
        ('groups', '0047_add_group_newcomer_role'),
    ]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        GroupMembership = apps.get_model('groups', 'GroupMembership')

        group = Group.objects.create(name=faker.name())
        user1 = User.objects.create(username=faker.user_name())
        user2 = User.objects.create(username=faker.user_name())
        user3 = User.objects.create(username=faker.user_name())
        self.membership1_id = GroupMembership.objects.create(group=group, user=user1, roles=['member']).id
        self.membership2_id = GroupMembership.objects.create(group=group, user=user2, roles=['member', 'editor']).id
        self.membership3_id = GroupMembership.objects.create(group=group, user=user3, roles=['member', 'foo']).id

    def tests_adds_newcomer_role(self):
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        membership1 = GroupMembership.objects.get(id=self.membership1_id)
        membership2 = GroupMembership.objects.get(id=self.membership2_id)
        membership3 = GroupMembership.objects.get(id=self.membership3_id)
        self.assertEqual(membership1.roles, ['member', 'newcomer'])
        self.assertEqual(membership2.roles, ['member', 'editor'])
        self.assertEqual(membership3.roles, ['member', 'foo'])
