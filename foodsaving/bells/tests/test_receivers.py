from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase

from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.bells.models import Bell, BellType
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestBellReceivers(TestCase):
    def test_creates_user_became_editor(self):
        user = UserFactory()
        group = GroupFactory(newcomers=[user])
        membership = GroupMembership.objects.get(user=user, group=group)
        self.assertFalse(Bell.objects.filter(user=user, type=BellType.USER_BECAME_EDITOR.value).exists())

        membership.roles.append(GROUP_EDITOR)
        membership.save()

        self.assertTrue(Bell.objects.filter(user=user, type=BellType.USER_BECAME_EDITOR.value).exists())

    def test_creates_new_applicant_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        self.assertFalse(Bell.objects.filter(user=member, type=BellType.NEW_APPLICANT.value).exists())

        user = UserFactory()
        GroupApplicationFactory(user=user, group=group)

        self.assertTrue(Bell.objects.filter(user=member, type=BellType.NEW_APPLICANT.value).exists())

    def test_creates_application_accepted_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.accept(member)

        self.assertTrue(Bell.objects.filter(user=user, type=BellType.APPLICATION_ACCEPTED.value).exists())
        self.assertTrue(Bell.objects.filter(user=member, type=BellType.APPLICATION_ACCEPTED.value).exists())

    def test_creates_application_declined_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.decline(member)

        self.assertTrue(Bell.objects.filter(user=user, type=BellType.APPLICATION_DECLINED.value).exists())
        self.assertTrue(Bell.objects.filter(user=member, type=BellType.APPLICATION_DECLINED.value).exists())

    def test_creates_feedback_possible_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        store = StoreFactory(group=group)
        pickup = PickupDateFactory(store=store)

        pickup.collectors.add(member)
        pickup.done_and_processed = True
        pickup.save()

        bell = Bell.objects.filter(user=member, type=BellType.FEEDBACK_POSSIBLE.value)
        self.assertTrue(bell.exists())
        self.assertLessEqual(bell[0].expires_at, pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS))
