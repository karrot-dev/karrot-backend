import os

from django.core import mail
from django.db import transaction
from django.test import TransactionTestCase

from karrot.groups.factories import GroupFactory
from karrot.offers.factories import OfferFactory
from karrot.tests.utils import execute_scheduled_tasks_immediately
from karrot.users.factories import VerifiedUserFactory

image_path = os.path.join(os.path.dirname(__file__), './photo.jpg')


class TestTasks(TransactionTestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.other_user = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.other_user])

    def test_does_not_notify_user_about_own_offer(self):
        mail.outbox = []

        with execute_scheduled_tasks_immediately():
            with transaction.atomic():
                self.offer = OfferFactory(group=self.group, user=self.user, images=[image_path])

        email_addresses = [address for m in mail.outbox for address in m.to]
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(email_addresses, [self.other_user.email])
