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
        self.member1 = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(members=[self.member1, self.member2])

        now = timezone.now()

        inactive_email_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP)
        self.membership1 = GroupMembership.objects.get(group=self.group, user=self.member1)
        self.membership1.lastseen_at = inactive_email_date
        self.membership1.save()

        remove_email_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_REMOVED_FROM_GROUP + 1)
        self.membership2 = GroupMembership.objects.get(group=self.group, user=self.member2)
        self.membership2.lastseen_at = remove_email_date
        self.membership2.active = False
        self.membership2.save()

        mail.outbox = []

    def test_process_user_inactive(self):
        process_inactive_users()
        self.assertEqual(len(mail.outbox), 2)
        self.membership1.refresh_from_db()
        self.assertEqual(self.membership1.active, False)
        self.assertEqual(len(GroupMembership.objects.all()), 1)
        self.assertEqual(GroupMembership.objects.first(), self.member1)


