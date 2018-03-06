from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from django.test import TestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.tasks import process_inactive_users
from foodsaving.users.factories import UserFactory
from config import settings

from datetime import timedelta


class TestProcessInactiveUsers (TestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
#        self.deleted_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])

        now = timezone.now()

        inactive_email_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP + 1)
        self.membership1 = GroupMembership.objects.get(group=self.group, user=self.inactive_user)
        self.membership1.lastseen_at = inactive_email_date
        self.membership1.save()

#        remove_email_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_REMOVED_FROM_GROUP + 1)
#        self.membership2 = GroupMembership.objects.get(group=self.group, user=self.deleted_user)
#        self.membership2.lastseen_at = remove_email_date
#        self.membership2.active = False
#        self.membership2.save()

        mail.outbox = []

    def test_process_inactive_users_removes_one_user(self):
        process_inactive_users()
        self.assertEqual(len(GroupMembership.objects.all()), 2)

    def test_process_inactive_users_leaves_active_user_alone(self):
        process_inactive_users()
        activeMembership = GroupMembership.objects.get(group=self.group, user=self.active_user)
        self.assertEqual(activeMembership.inactive_at, None)

    def test_process_inactive_users_flags_inactive_user(self):
        process_inactive_users()
        self.membership1.refresh_from_db()
        self.assertNotEqual(self.membership1.inactive_at, None)

    def test_process_inactive_users_sends_email(self):
        process_inactive_users()
        self.assertEqual(len(mail.outbox), 1)


class TestProcessReallyInactiveUsers(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.membership = GroupMembership.objects.get(group=self.group, user=self.user)
        now = timezone.now()
        self.membership.lastseen_at = now - relativedelta(years=1)
        self.membership.save()
        mail.outbox = []

    def test_give_really_inactive_user_a_chance(self):
        process_inactive_users()
        process_inactive_users()
        self.assertTrue(GroupMembership.objects.filter(group=self.group, user=self.user).exists())



