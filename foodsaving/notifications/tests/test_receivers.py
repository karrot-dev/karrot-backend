from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase

from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.invitations.models import Invitation
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory


class TestNotificationReceivers(TestCase):
    def test_creates_user_became_editor(self):
        user = UserFactory()
        user1 = UserFactory()
        group = GroupFactory(newcomers=[user, user1])
        membership = GroupMembership.objects.get(user=user, group=group)
        notifications = Notification.objects.filter(type=NotificationType.USER_BECAME_EDITOR.value)
        self.assertEqual(notifications.count(), 0)

        membership.roles.append(GROUP_EDITOR)
        membership.save()

        self.assertEqual(notifications.count(), 2)
        self.assertEqual(set(notification.user for notification in notifications), {user, user1})

    def test_creates_new_applicant_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        self.assertEqual(
            Notification.objects.filter(user=member, type=NotificationType.NEW_APPLICANT.value).count(), 0
        )

        user = UserFactory()
        GroupApplicationFactory(user=user, group=group)

        self.assertEqual(
            Notification.objects.filter(user=member, type=NotificationType.NEW_APPLICANT.value).count(), 1
        )

    def test_removes_new_application_notification_when_decided(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        users = [UserFactory() for _ in range(3)]
        applications = [GroupApplicationFactory(user=user, group=group) for user in users]
        applications[0].withdraw()
        applications[1].accept(member)
        applications[2].decline(member)

        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_accepted_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.accept(member)

        self.assertEqual(
            Notification.objects.filter(user=user, type=NotificationType.APPLICATION_ACCEPTED.value).count(), 1
        )
        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_declined_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = GroupApplicationFactory(user=user, group=group)
        application.decline(member)

        self.assertEqual(
            Notification.objects.filter(user=user, type=NotificationType.APPLICATION_DECLINED.value).count(), 1
        )
        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_feedback_possible_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        store = StoreFactory(group=group)
        pickup = PickupDateFactory(store=store)

        pickup.add_collector(member)
        pickup.done_and_processed = True
        pickup.save()

        notification = Notification.objects.filter(user=member, type=NotificationType.FEEDBACK_POSSIBLE.value)
        self.assertEqual(notification.count(), 1)
        self.assertLessEqual(
            notification[0].expires_at, pickup.date + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)
        )

    def test_creates_new_store_notification(self):
        member = UserFactory()
        creator = UserFactory()
        group = GroupFactory(members=[member, creator])
        store = StoreFactory(group=group, created_by=creator)

        notifications = Notification.objects.filter(type=NotificationType.NEW_STORE.value)
        # creator does not get a notification
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications[0].user, member)
        self.assertEqual(notifications[0].context['store'], store.id)
        self.assertEqual(notifications[0].context['user'], creator.id)

    def test_creates_new_member_notification(self):
        member1 = UserFactory()
        member2 = UserFactory()
        group = GroupFactory(members=[member1, member2])
        Notification.objects.all().delete()

        user = UserFactory()
        group.add_member(user, added_by=member1)

        notifications = Notification.objects.filter(type=NotificationType.NEW_MEMBER.value)
        # member1 doesn't get a notification, as they added the user
        self.assertEqual(notifications.count(), 1, notifications)
        self.assertEqual(notifications[0].user, member2)

    def test_creates_new_invitation_accepted_notification(self):
        member1 = UserFactory()
        member2 = UserFactory()
        group = GroupFactory(members=[member1, member2])
        invitation = Invitation.objects.create(email='bla@bla.com', group=group, invited_by=member1)
        Notification.objects.all().delete()

        user = UserFactory()
        invitation.accept(user)

        notifications = Notification.objects.filter(type=NotificationType.INVITATION_ACCEPTED.value)
        # only member1 gets a notification, as they invited the user
        # other group members already get the new_member notification
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications[0].user, member1)
        context = notifications[0].context
        self.assertEqual(context['group'], group.id)
        self.assertEqual(context['user'], user.id)
