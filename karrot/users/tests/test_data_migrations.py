import string

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from karrot.tests.utils import TestMigrations


class TestGenerateUsername(TestMigrations):
    migrate_from = [
        ('users', '0023_user_username'),
    ]
    migrate_to = [
        ('users', '0024_generate_usernames'),
    ]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        self.id1 = User.objects.create(display_name='Peter Jones').id
        self.id2 = User.objects.create(display_name='Peter Jones').id
        self.id3 = User.objects.create(display_name='Peter Jones').id
        self.id4 = User.objects.create(display_name='Peter Jones').id
        self.id5 = User.objects.create(display_name='Peter Jones').id
        self.id6 = User.objects.create(display_name='Peter Jones').id

        self.id7 = User.objects.create(email='JaMiE@gmail.com').id
        self.id8 = User.objects.create(email='JaMiE@hotmail.com').id

        self.id9 = User.objects.create(display_name='Peter Jones', email='JaMiE@yahoo.com').id

        self.id10 = User.objects.create().id

        # gives people who logged in more recently better usernames
        ages_ago = timezone.now() - relativedelta(years=4)
        just_the_other_day = timezone.now() - relativedelta(days=4)
        self.id11 = User.objects.create(display_name='nick', last_login=ages_ago).id
        self.id12 = User.objects.create(display_name='nick', last_login=just_the_other_day).id

    def test_username_creation(self):
        User = self.apps.get_model('users', 'User')

        self.check_username(self.id1, 'peter')
        self.check_username(self.id2, 'peterjones')
        self.check_username(self.id3, 'peter1')
        self.check_username(self.id4, 'peterjones1')
        self.check_username(self.id5, 'peter2')
        self.check_username(self.id6, 'peterjones2')

        self.check_username(self.id7, 'jamie')
        self.check_username(self.id8, 'jamie1')

        self.check_username(self.id9, 'jamie2')

        allowed = set(string.ascii_lowercase + string.digits)
        user = User.objects.get(id=self.id10)
        self.assertEqual(len(user.username), 8)
        self.assertTrue(set(user.username) <= allowed)

        self.check_username(self.id11, 'nick1')
        self.check_username(self.id12, 'nick')

    def check_username(self, id, username):
        User = self.apps.get_model('users', 'User')
        self.assertEqual(User.objects.get(id=id).username, username)
