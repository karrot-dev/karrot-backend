from dateutil.relativedelta import relativedelta
from django.core import mail
from django.test import TestCase
from freezegun import freeze_time

from karrot.issues.factories import IssueFactory
from karrot.issues.models import OptionTypes
from karrot.issues.tasks import process_expired_votings
from karrot.groups import roles
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupNotificationType
from karrot.groups.roles import GROUP_EDITOR
from karrot.history.models import History, HistoryTypus
from karrot.users.factories import VerifiedUserFactory


class IssueModelTests(TestCase):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.affected_member])
        self.issue = IssueFactory(group=self.group, created_by=self.member, affected_user=self.affected_member)

        # add notification type to send out emails
        for membership in self.group.groupmembership_set.all():
            membership.add_notification_types([GroupNotificationType.CONFLICT_RESOLUTION])
            membership.save()

    def get_voting(self):
        return self.issue.votings.first()

    def vote_on(self, option_type, user=None):
        for option in self.get_voting().options.all():
            option.votes.create(user=user or self.member, score=5 if option.type == option_type else 0)

    def fast_forward_to_voting_expiration(self):
        time_when_voting_expires = self.get_voting().expires_at + relativedelta(hours=1)
        return freeze_time(time_when_voting_expires, tick=True)

    def process_votings(self):
        with self.fast_forward_to_voting_expiration():
            process_expired_votings()

    def create_editor(self):
        user = VerifiedUserFactory()
        self.group.groupmembership_set.create(user=user, roles=[GROUP_EDITOR])
        return user

    def test_removes_user(self):
        self.vote_on(OptionTypes.REMOVE_USER.value)
        History.objects.all().delete()
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.issue.refresh_from_db()
            self.assertTrue(self.issue.is_decided())
            self.assertFalse(self.group.is_member(self.affected_member))
            self.assertEqual(self.issue.votings.count(), 1)
            self.assertTrue(self.get_voting().is_expired())

        self.assertEqual(History.objects.count(), 1)
        self.assertEqual(History.objects.first().typus, HistoryTypus.MEMBER_REMOVED)

    def test_further_discussion(self):
        self.vote_on(OptionTypes.FURTHER_DISCUSSION.value)
        mail.outbox = []
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.issue.refresh_from_db()
            self.assertFalse(self.issue.is_decided())
            self.assertTrue(self.group.is_member(self.affected_member))
            self.assertEqual(self.issue.votings.count(), 2)
            self.assertEqual([v.is_expired() for v in self.issue.votings.order_by('created_at')], [True, False])

        # check if emails have been sent
        self.assertEqual(len(mail.outbox), 2)
        email_to_affected_user = next(email for email in mail.outbox if email.to[0] == self.affected_member.email)
        email_to_editor = next(email for email in mail.outbox if email.to[0] == self.member.email)
        self.assertIn('with you', email_to_affected_user.subject)
        self.assertIn('with {}'.format(self.affected_member.display_name), email_to_editor.subject)

    def test_no_change(self):
        self.vote_on(OptionTypes.NO_CHANGE.value)
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.issue.refresh_from_db()
            self.assertTrue(self.issue.is_decided())
            self.assertTrue(self.group.is_member(self.affected_member))
            self.assertEqual(self.issue.votings.count(), 1)
            self.assertTrue(self.get_voting().is_expired())

    def test_tie_results_in_further_discussion(self):
        self.vote_on(OptionTypes.NO_CHANGE.value, user=self.member)
        voter = self.create_editor()
        self.vote_on(OptionTypes.REMOVE_USER.value, user=voter)
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.assertEqual(self.get_voting().accepted_option.type, OptionTypes.FURTHER_DISCUSSION.value)

    def test_no_vote_results_in_cancelled_issue(self):
        self.process_votings()

        self.issue.refresh_from_db()
        self.assertTrue(self.issue.is_cancelled())

    def test_voluntary_user_removal_results_in_cancelled_issue(self):
        self.group.groupmembership_set.filter(user=self.affected_member).delete()

        self.issue.refresh_from_db()
        self.assertTrue(self.issue.is_cancelled())

    def test_new_members_are_not_in_existing_issues(self):
        # create a new member and a new editor
        self.group.groupmembership_set.create(user=VerifiedUserFactory(), roles=[roles.GROUP_EDITOR])
        self.group.groupmembership_set.create(user=VerifiedUserFactory())

        # ...but they shouldn't become part of existing issues
        expected_ids = sorted([self.member.id, self.affected_member.id])
        participant_ids = sorted(self.issue.participants.values_list('id', flat=True))
        conversation_participant_ids = sorted(self.issue.conversation.participants.values_list('id', flat=True))
        self.assertEqual(participant_ids, expected_ids)
        self.assertEqual(conversation_participant_ids, expected_ids)

    def test_remove_participant_if_they_leave_group(self):
        self.assertTrue(self.issue.participants.filter(id=self.member.id).exists())
        self.assertTrue(self.issue.conversation.participants.filter(id=self.member.id).exists())

        self.group.groupmembership_set.filter(user=self.member).delete()

        self.assertFalse(self.issue.participants.filter(id=self.member.id).exists())
        self.assertFalse(self.issue.conversation.participants.filter(id=self.member.id).exists())
