import json
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from pprint import pprint
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.cases.factories import CaseFactory
from foodsaving.cases.models import Voting
from foodsaving.cases.tasks import process_expired_votings
from foodsaving.conversations.models import Conversation
from foodsaving.groups.factories import GroupFactory
from foodsaving.applications.factories import GroupApplicationFactory
from foodsaving.groups.models import GroupMembership, GroupNotificationType
from foodsaving.applications.models import GroupApplicationStatus
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory, VerifiedUserFactory
from foodsaving.users.serializers import UserSerializer
from foodsaving.utils.tests.fake import faker


class TestConflictResolutionAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.affected_member])

    def test_create_conflict_resolution_case(self):
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

        # get conversation
        response = self.client.get('/api/cases/{}/conversation/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        voting = case['votings'][0]

        # vote on option
        options = voting['options']
        for score, option in zip([1, 5], options):
            response = self.client.post('/api/cases-votes/', {
                'option': option['id'],
                'score': score,
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # get results
        time_when_voting_expires = parse(voting['expires_at']) + relativedelta(hours=1)
        with freeze_time(time_when_voting_expires, tick=True):
            process_expired_votings()
            response = self.client.get('/api/cases/{}/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


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

    def create_case_via_API(self):
        return self.client.post(
            '/api/cases/', {
                'group': self.group.id,
                'topic': 'asdf',
                'affected_user': self.affected_member.id,
            }
        )

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
