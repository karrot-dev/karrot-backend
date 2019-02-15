from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from karrot.applications.factories import ApplicationFactory
from karrot.groups.factories import GroupFactory, PlaygroundGroupFactory
from karrot.groups.models import GroupMembership
from karrot.groups.roles import GROUP_EDITOR
from karrot.invitations.models import Invitation
from karrot.issues.factories import IssueFactory, vote_for_further_discussion, fast_forward_to_voting_expiration, \
    vote_for_remove_user
from karrot.issues.tasks import process_expired_votings
from karrot.notifications.models import Notification, NotificationType
from karrot.notifications.tasks import create_pickup_upcoming_notifications
from karrot.pickups.factories import PickupDateFactory
from karrot.pickups.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestNotificationReceivers(TestCase):
    def test_creates_user_became_editor(self):
        user = UserFactory()
        user1 = UserFactory()
        group = GroupFactory(newcomers=[user, user1])
        membership = GroupMembership.objects.get(user=user, group=group)
        Notification.objects.all().delete()

        membership.roles.append(GROUP_EDITOR)
        membership.save()

        self.assertEqual(Notification.objects.count(), 2)
        you_became_editor = Notification.objects.get(type=NotificationType.YOU_BECAME_EDITOR.value)
        self.assertEqual(you_became_editor.user, user)
        user_became_editor = Notification.objects.get(type=NotificationType.USER_BECAME_EDITOR.value)
        self.assertEqual(user_became_editor.user, user1)

    def test_prevent_user_became_editor_when_joining_playground(self):
        user1 = UserFactory()
        group = PlaygroundGroupFactory(newcomers=[user1])
        Notification.objects.all().delete()

        user = UserFactory()
        group.add_member(user)

        self.assertEqual(Notification.objects.count(), 1)
        you_became_editor = Notification.objects.get(type=NotificationType.YOU_BECAME_EDITOR.value)
        self.assertEqual(you_became_editor.user, user)

    def test_creates_new_applicant_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        self.assertEqual(
            Notification.objects.filter(user=member, type=NotificationType.NEW_APPLICANT.value).count(), 0
        )

        user = UserFactory()
        ApplicationFactory(user=user, group=group)

        self.assertEqual(
            Notification.objects.filter(user=member, type=NotificationType.NEW_APPLICANT.value).count(), 1
        )

    def test_removes_new_application_notification_when_decided(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        users = [UserFactory() for _ in range(3)]
        applications = [ApplicationFactory(user=user, group=group) for user in users]
        applications[0].withdraw()
        applications[1].accept(member)
        applications[2].decline(member)

        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_accepted_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = ApplicationFactory(user=user, group=group)
        application.accept(member)

        self.assertEqual(
            Notification.objects.filter(user=user, type=NotificationType.APPLICATION_ACCEPTED.value).count(), 1
        )
        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_application_declined_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])

        user = UserFactory()
        application = ApplicationFactory(user=user, group=group)
        application.decline(member)

        self.assertEqual(
            Notification.objects.filter(user=user, type=NotificationType.APPLICATION_DECLINED.value).count(), 1
        )
        self.assertEqual(Notification.objects.filter(type=NotificationType.NEW_APPLICANT.value).count(), 0)

    def test_creates_feedback_possible_notification(self):
        member = UserFactory()
        group = GroupFactory(members=[member])
        place = PlaceFactory(group=group)
        pickup = PickupDateFactory(place=place)

        pickup.add_collector(member)
        pickup.is_done = True
        pickup.save()

        notification = Notification.objects.filter(user=member, type=NotificationType.FEEDBACK_POSSIBLE.value)
        self.assertEqual(notification.count(), 1)
        self.assertLessEqual(
            notification[0].expires_at, pickup.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)
        )

    def test_creates_new_place_notification(self):
        member = UserFactory()
        creator = UserFactory()
        group = GroupFactory(members=[member, creator])
        place = PlaceFactory(group=group, last_changed_by=creator)

        notifications = Notification.objects.filter(type=NotificationType.NEW_PLACE.value)
        # creator does not get a notification
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications[0].user, member)
        self.assertEqual(notifications[0].context['place'], place.id)
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
        self.assertEqual(notifications[0].context['user'], user.id)

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

    def test_deletes_pickup_upcoming_notification(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        in_one_hour = to_range(timezone.now() + relativedelta(hours=1))
        pickup = PickupDateFactory(place=place, date=in_one_hour, collectors=[user])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        pickup.remove_collector(user)

        notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(notifications.count(), 0)

    def test_creates_pickup_disabled_notification_and_deletes_pickup_upcoming_notification(self):
        user1, user2 = UserFactory(), UserFactory()
        group = GroupFactory(members=[user1, user2])
        place = PlaceFactory(group=group)
        in_one_hour = to_range(timezone.now() + relativedelta(hours=1))
        pickup = PickupDateFactory(place=place, date=in_one_hour, collectors=[user1, user2])
        Notification.objects.all().delete()

        create_pickup_upcoming_notifications.call_local()
        pickup.last_changed_by = user2
        pickup.is_disabled = True
        pickup.save()

        pickup_upcoming_notifications = Notification.objects.filter(type=NotificationType.PICKUP_UPCOMING.value)
        self.assertEqual(pickup_upcoming_notifications.count(), 0)

        pickup_disabled_notifications = Notification.objects.filter(type=NotificationType.PICKUP_DISABLED.value)
        self.assertEqual(pickup_disabled_notifications.count(), 1)
        self.assertEqual(pickup_disabled_notifications[0].user, user1)
        context = pickup_disabled_notifications[0].context
        self.assertEqual(context['group'], group.id)
        self.assertEqual(context['pickup'], pickup.id)
        self.assertEqual(context['place'], place.id)

    def test_creates_pickup_enabled_notification(self):
        user1, user2 = UserFactory(), UserFactory()
        group = GroupFactory(members=[user1, user2])
        place = PlaceFactory(group=group)
        pickup = PickupDateFactory(place=place, collectors=[user1, user2])
        Notification.objects.all().delete()

        pickup.last_changed_by = user2
        pickup.is_disabled = True
        pickup.save()

        pickup.is_disabled = False
        pickup.save()

        pickup_enabled_notifications = Notification.objects.filter(type=NotificationType.PICKUP_ENABLED.value)
        self.assertEqual(pickup_enabled_notifications.count(), 1)
        self.assertEqual(pickup_enabled_notifications[0].user, user1)
        context = pickup_enabled_notifications[0].context
        self.assertEqual(context['group'], group.id)
        self.assertEqual(context['pickup'], pickup.id)
        self.assertEqual(context['place'], place.id)

    def test_creates_pickup_moved_notification(self):
        user1, user2 = UserFactory(), UserFactory()
        group = GroupFactory(members=[user1, user2])
        place = PlaceFactory(group=group)
        pickup = PickupDateFactory(place=place, collectors=[user1, user2])
        Notification.objects.all().delete()

        pickup.last_changed_by = user2
        pickup.date = pickup.date + relativedelta(days=2)
        pickup.save()

        notifications = Notification.objects.all()
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications[0].type, NotificationType.PICKUP_MOVED.value)
        self.assertEqual(notifications[0].user, user1)
        context = notifications[0].context
        self.assertEqual(context['group'], group.id)
        self.assertEqual(context['pickup'], pickup.id)
        self.assertEqual(context['place'], place.id)

    def test_conflict_resolution_notifications(self):
        user1, user2, user3 = UserFactory(), UserFactory(), UserFactory()
        group = GroupFactory(members=[user1, user2, user3])
        Notification.objects.all().delete()

        issue = IssueFactory(group=group, created_by=user1, affected_user=user2)

        notifications = Notification.objects.order_by('type')
        self.assertEqual(notifications.count(), 2)
        self.assertEqual(notifications[1].type, NotificationType.CONFLICT_RESOLUTION_CREATED_ABOUT_YOU.value)
        self.assertEqual(notifications[1].user, user2)
        self.assertEqual(notifications[1].context, {'issue': issue.id, 'group': group.id, 'user': user2.id})
        self.assertEqual(notifications[0].type, NotificationType.CONFLICT_RESOLUTION_CREATED.value)
        self.assertEqual(notifications[0].user, user3)

        # keep discussing
        Notification.objects.all().delete()
        voting = issue.latest_voting()
        vote_for_further_discussion(voting=voting, user=user1)
        with fast_forward_to_voting_expiration(voting):
            process_expired_votings()

        notifications = Notification.objects.order_by('type')
        self.assertEqual(notifications.count(), 3)
        self.assertEqual(notifications[0].type, NotificationType.CONFLICT_RESOLUTION_CONTINUED.value)
        self.assertEqual(notifications[1].type, NotificationType.CONFLICT_RESOLUTION_CONTINUED.value)
        self.assertEqual(notifications[2].type, NotificationType.CONFLICT_RESOLUTION_CONTINUED_ABOUT_YOU.value)

        # remove user
        Notification.objects.all().delete()
        voting = issue.latest_voting()
        vote_for_remove_user(voting=voting, user=user1)
        with fast_forward_to_voting_expiration(voting):
            process_expired_votings()

        notifications = Notification.objects.order_by('type')
        self.assertEqual(notifications.count(), 4)
        self.assertEqual([n.type for n in notifications], [
            NotificationType.CONFLICT_RESOLUTION_DECIDED.value,
            NotificationType.CONFLICT_RESOLUTION_DECIDED.value,
            NotificationType.CONFLICT_RESOLUTION_DECIDED_ABOUT_YOU.value,
            NotificationType.CONFLICT_RESOLUTION_YOU_WERE_REMOVED.value,
        ])
