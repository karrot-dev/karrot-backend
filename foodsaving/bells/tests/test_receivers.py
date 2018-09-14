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
        self.assertEqual(Bell.objects.filter(user=user, type=BellType.USER_BECAME_EDITOR.value).count(), 0)

        membership.roles.append(GROUP_EDITOR)
        membership.save()

        self.assertEqual(Bell.objects.filter(user=user, type=BellType.USER_BECAME_EDITOR.value).count(), 1)

    def test_creates_new_applicant_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        self.assertEqual(Bell.objects.filter(user=member, type=BellType.NEW_APPLICANT.value).count(), 0)

        user = UserFactory()
        GroupApplicationFactory(user=user, group=group)

        self.assertEqual(Bell.objects.filter(user=member, type=BellType.NEW_APPLICANT.value).count(), 1)

    def test_removes_new_application_bell_when_decided(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        users = [UserFactory() for _ in range(3)]
        applications = [GroupApplicationFactory(user=user, group=group) for user in users]
        applications[0].withdraw()
        applications[1].accept(member)
        applications[2].decline(member)

        self.assertEqual(Bell.objects.filter(type=BellType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_accepted_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.accept(member)

        self.assertEqual(Bell.objects.filter(user=user, type=BellType.APPLICATION_ACCEPTED.value).count(), 1)
        self.assertEqual(Bell.objects.filter(user=member, type=BellType.APPLICATION_ACCEPTED.value).count(), 1)
        self.assertEqual(Bell.objects.filter(type=BellType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_declined_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.decline(member)

        self.assertEqual(Bell.objects.filter(user=user, type=BellType.APPLICATION_DECLINED.value).count(), 1)
        self.assertEqual(Bell.objects.filter(user=member, type=BellType.APPLICATION_DECLINED.value).count(), 1)
        self.assertEqual(Bell.objects.filter(type=BellType.NEW_APPLICANT.value).count(), 0)

    def test_creates_feedback_possible_bell(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        store = StoreFactory(group=group)
        pickup = PickupDateFactory(store=store)

        pickup.collectors.add(member)
        pickup.done_and_processed = True
        pickup.save()

        bell = Bell.objects.filter(user=member, type=BellType.FEEDBACK_POSSIBLE.value)
        self.assertEqual(bell.count(), 1)
        self.assertLessEqual(bell[0].expires_at, pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS))

    def test_creates_new_store_bell(self):
        member = UserFactory()
        creator = UserFactory()
        group = GroupFactory(members=[member, creator])
        store = StoreFactory(group=group, created_by=creator)

        bells = Bell.objects.filter(type=BellType.NEW_STORE.value)
        self.assertEqual(bells.count(), 1)
        self.assertEqual(bells[0].user, member)
        self.assertEqual(bells[0].payload['store'], store.id)
        self.assertEqual(bells[0].payload['user'], creator.id)
