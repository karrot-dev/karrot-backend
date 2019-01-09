from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from pprint import pprint
from rest_framework import status
from rest_framework.test import APITestCase

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
        self.voters = [VerifiedUserFactory() for _ in range(5)]
        self.group = GroupFactory(members=[self.member, self.affected_member, *self.voters])

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

        # vote on proposal
        proposals = voting['proposals']
        response = self.client.post('/api/cases-votes/', {
            'proposal': proposals[0]['id'],
            'score': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # get results
        time_when_voting_expires = parse(voting['expires_at']) + relativedelta(hours=1)
        with freeze_time(time_when_voting_expires, tick=True):
            response = self.client.get('/api/cases/{}/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        case = response.data

        pprint(case)
