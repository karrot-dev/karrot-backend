from dateutil.relativedelta import relativedelta
from django.test import TestCase
from freezegun import freeze_time

from foodsaving.cases.factories import CaseFactory
from foodsaving.cases.models import OptionTypes
from foodsaving.cases.tasks import process_expired_votings
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.users.factories import VerifiedUserFactory


class CaseModelTests(TestCase):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.affected_member])
        self.case = CaseFactory(group=self.group, created_by=self.member, affected_user=self.affected_member)

    def get_voting(self):
        return self.case.votings.first()

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
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.case.refresh_from_db()
            self.assertTrue(self.case.is_decided)
            self.assertFalse(self.group.is_member(self.affected_member))
            self.assertEqual(self.case.votings.count(), 1)
            self.assertTrue(self.get_voting().is_expired())

    def test_further_discussion(self):
        self.vote_on(OptionTypes.FURTHER_DISCUSSION.value)
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.case.refresh_from_db()
            self.assertFalse(self.case.is_decided)
            self.assertTrue(self.group.is_member(self.affected_member))
            self.assertEqual(self.case.votings.count(), 2)
            self.assertEqual([v.is_expired() for v in self.case.votings.order_by('created_at')], [True, False])

    def test_no_change(self):
        self.vote_on(OptionTypes.NO_CHANGE.value)
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.case.refresh_from_db()
            self.assertTrue(self.case.is_decided)
            self.assertTrue(self.group.is_member(self.affected_member))
            self.assertEqual(self.case.votings.count(), 1)
            self.assertTrue(self.get_voting().is_expired())

    def test_tie_results_in_further_discussion(self):
        self.vote_on(OptionTypes.NO_CHANGE.value, user=self.member)
        voter = self.create_editor()
        self.vote_on(OptionTypes.REMOVE_USER.value, user=voter)
        self.process_votings()

        with self.fast_forward_to_voting_expiration():
            self.assertEqual(self.get_voting().accepted_option.type, OptionTypes.FURTHER_DISCUSSION.value)
