from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.cases.factories import CaseFactory
from foodsaving.cases.tasks import process_expired_votings
from foodsaving.groups.factories import GroupFactory
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import VerifiedUserFactory


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
        options = voting['options']
        for score, option in zip([1, 5], options):
            response = self.client.post(
                '/api/cases/options/{}/vote/'.format(option['id']),
                {'score': score}, format='json'
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

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
        option = case.votings.first().options.first()

        response = self.client.post('/api/cases/options/{}/vote/'.format(option.id), {'score': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.client.post('/api/cases/options/{}/vote/'.format(option.id), {'score': 2}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        option.refresh_from_db()
        self.assertEqual(option.votes.first().score, 2)

        response = self.client.delete('/api/cases/options/{}/vote/'.format(option.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        option.refresh_from_db()
        self.assertEqual(option.votes.count(), 0)


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

    def vote_via_API(self, option_id):
        return self.client.post('/api/cases/options/{}/vote/'.format(option_id), {'score': 1}, format='json')

    def delete_vote_via_API(self, option_id):
        return self.client.delete('/api/cases/options/{}/vote/'.format(option_id))

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
        option = case.votings.first().options.first()
        response = self.vote_via_API(option.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        option = case.votings.first().options.first()
        response = self.vote_via_API(option.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        option = case.votings.first().options.first()
        response = self.delete_vote_via_API(option.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        option = case.votings.first().options.first()
        response = self.delete_vote_via_API(option.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
