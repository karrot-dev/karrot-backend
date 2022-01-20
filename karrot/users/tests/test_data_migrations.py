import string

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from karrot.tests.utils import TestMigrations


class TestGenerateUsername(TestMigrations):
    migrate_from = [
        ('users', '0023_user_username'),
        ('groups', '0043_auto_20200717_1325'),
    ]
    migrate_to = [
        ('users', '0024_generate_usernames'),
    ]

    def create_user(self, **kwargs):
        User = self.apps.get_model('users', 'User')
        GroupMembership = self.apps.get_model('groups', 'GroupMembership')
        user = User.objects.create(**kwargs)
        GroupMembership.objects.create(user=user, group=self.group)
        return user

    def setUpBeforeMigration(self, apps):
        self.apps = apps
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        self.group = Group.objects.create(name='testgroup')
        self.id1 = self.create_user(display_name='Peter Jones').id
        self.id2 = self.create_user(display_name='Peter Jones').id
        self.id3 = self.create_user(display_name='Peter Jones').id
        self.id4 = self.create_user(display_name='Peter Jones').id
        self.id5 = self.create_user(display_name='Peter Jones').id
        self.id6 = self.create_user(display_name='Peter Jones').id

        self.id7 = self.create_user(email='JaMiE@gmail.com').id
        self.id8 = self.create_user(email='JaMiE@hotmail.com').id

        self.id9 = User.objects.create(display_name='Peter Jones', email='JaMiE@yahoo.com').id

        self.id10 = User.objects.create().id

        # gives people who logged in more recently better usernames
        ages_ago = timezone.now() - relativedelta(years=4)
        just_the_other_day = timezone.now() - relativedelta(days=4)
        self.id11 = User.objects.create(display_name='nick', last_login=ages_ago).id
        self.id12 = User.objects.create(display_name='nick', last_login=just_the_other_day).id

    def test_username_creation(self):
        User = self.apps.get_model('users', 'User')

        self.check_username(self.id6, 'peter')
        self.check_username(self.id5, 'peterjones')
        self.check_username(self.id4, 'peter1')
        self.check_username(self.id3, 'peterjones1')
        self.check_username(self.id2, 'peter2')
        self.check_username(self.id1, 'peterjones2')

        self.check_username(self.id8, 'jamie')
        self.check_username(self.id7, 'jamie1')

        self.check_username(self.id9, 'jamie2')

        allowed = set(string.ascii_lowercase + string.digits)
        user = User.objects.get(id=self.id10)
        self.assertEqual(len(user.username), 8)
        self.assertTrue(set(user.username) <= allowed)

        self.check_username(self.id12, 'nick')
        self.check_username(self.id11, 'nick1')

    def check_username(self, id, username):
        User = self.apps.get_model('users', 'User')
        self.assertEqual(User.objects.get(id=id).username, username)
