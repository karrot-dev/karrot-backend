from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.cases.factories import CaseFactory
from foodsaving.cases.models import Vote
from foodsaving.cases.tasks import process_expired_votings
from foodsaving.groups.factories import GroupFactory
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import VerifiedUserFactory


def make_vote_data(options, scores=None):
    if scores is None:
        scores = [1] * len(options)

    def get_id(o):
        return getattr(o, 'id', None) or o['id']

    return [{'option': get_id(o), 'score': s} for o, s in zip(options, scores)]


class TestConflictResolutionAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.affected_member])

    def create_case(self, **kwargs):
        return CaseFactory(group=self.group, created_by=self.member, **kwargs)

    def test_create_conflict_resolution_case_and_vote(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            '/api/cases/', {
                'group': self.group.id,
                'topic': 'I complain about this user',
                'affected_user': self.affected_member.id,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        case = response.data
        self.assertEqual(case['created_by'], self.member.id)
        self.assertFalse(case['is_decided'])
        self.assertEqual(case['type'], 'conflict_resolution')
        self.assertEqual(case['topic'], 'I complain about this user')
        self.assertEqual(case['group'], self.group.id)
        self.assertEqual(case['affected_user'], self.affected_member.id)
        self.assertEqual(len(case['votings']), 1)
        self.assertLessEqual(parse(case['created_at']), timezone.now())

        voting = case['votings'][0]

        # vote on option
        response = self.client.post(
            '/api/cases/votings/{}/vote/'.format(voting['id']), make_vote_data(voting['options']), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        votes = response.data
        self.assertEqual(len(votes), 3)
        self.assertIn('option', votes[0])
        self.assertIn('score', votes[0])

        # get results
        time_when_voting_expires = parse(voting['expires_at']) + relativedelta(hours=1)
        with freeze_time(time_when_voting_expires, tick=True):
            process_expired_votings()
            response = self.client.get('/api/cases/{}/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # get conversation
        response = self.client.get('/api/cases/{}/conversation/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_vote_can_be_updated_and_deleted(self):
        self.client.force_login(user=self.member)
        case = self.create_case()
        voting = case.votings.first()
        options = voting.options.all()
        option_count = options.count()

        response = self.client.post(
            '/api/cases/votings/{}/vote/'.format(voting.id),
            make_vote_data(options, [1] * option_count),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.client.post(
            '/api/cases/votings/{}/vote/'.format(voting.id),
            make_vote_data(options, [2] * option_count),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.assertEqual([v.score for v in Vote.objects.all()], [2] * option_count)

        response = self.client.delete('/api/cases/votings/{}/vote/'.format(voting.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        self.assertEqual(Vote.objects.count(), 0)


class TestCaseAPIPermissions(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(
            members=[self.member, self.affected_member],
            newcomers=[self.newcomer],
        )

    def create_case(self, **kwargs):
        return CaseFactory(group=self.group, created_by=self.member, **kwargs)

    def create_case_via_API(self, **kwargs):
        return self.client.post(
            '/api/cases/', {
                'group': self.group.id,
                'topic': 'asdf',
                'affected_user': kwargs.get('affected_user', self.affected_member).id,
            },
            format='json'
        )

    def vote_via_API(self, voting, data=None):
        return self.client.post(
            '/api/cases/votings/{}/vote/'.format(voting.id),
            data or make_vote_data(voting.options.all()),
            format='json'
        )

    def fast_forward_to_voting_expiration(self, voting):
        time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
        return freeze_time(time_when_voting_expires, tick=True)

    def delete_vote_via_API(self, voting):
        return self.client.delete('/api/cases/votings/{}/vote/'.format(voting.id))

    def test_cannot_create_case_as_nonmember(self):
        self.client.force_login(user=VerifiedUserFactory())
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_case_as_newcomer(self):
        self.client.force_login(user=self.newcomer)
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_twice_for_same_person(self):
        self.client.force_login(user=self.member)
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_case_about_nonmember(self):
        self.client.force_login(user=self.member)
        response = self.create_case_via_API(affected_user=VerifiedUserFactory())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_list_cases_as_nonmember(self):
        self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/cases/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_list_cases_as_newcomer(self):
        self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/cases/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_retrieve_cases_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.get_results('/api/cases/{}/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_cases_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/cases/{}/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.vote_via_API(case.votings.first())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.vote_via_API(case.votings.first())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.delete_vote_via_API(case.votings.first())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.delete_vote_via_API(case.votings.first())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_in_expired_voting(self):
        case = self.create_case()
        voting = case.votings.first()
        self.client.force_login(user=self.member)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_change_vote_in_expired_voting(self):
        case = self.create_case()
        voting = case.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_delete_vote_in_expired_voting(self):
        case = self.create_case()
        voting = case.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.delete_vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_must_provide_score_for_all_options_in_voting(self):
        case = self.create_case()
        voting = case.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(voting, data=[{'option': voting.options.first().id, 'score': 1}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual('You need to provide a score for all options', response.data['non_field_errors'][0])

    def test_cannot_provide_score_for_options_in_other_voting(self):
        case = self.create_case()
        voting = case.votings.first()
        case2 = self.create_case()
        voting2 = case2.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(voting, data=[{'option': voting2.options.first().id, 'score': 1}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual('Provided option is not part of this voting', response.data[0]['option'][0])

    def test_cannot_create_case_against_yourself(self):
        pass
