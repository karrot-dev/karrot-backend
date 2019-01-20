from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.cases.factories import CaseFactory, vote_for_remove_user
from foodsaving.cases.models import Vote, CaseStatus
from foodsaving.cases.tasks import process_expired_votings
from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupNotificationType
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
        settings.CONFLICT_RESOLUTION_ACTIVE_EDITORS_REQUIRED_FOR_CREATION = 1
        self.member = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.member, self.affected_member])

        # effectively disable throttling
        from foodsaving.cases.api import ConflictResolutionThrottle
        ConflictResolutionThrottle.rate = '1000/min'

    def create_case(self, **kwargs):
        return CaseFactory(group=self.group, created_by=self.member, **kwargs)

    def test_create_conflict_resolution_case_and_vote(self):
        # add another editor
        notification_member = VerifiedUserFactory()
        self.group.groupmembership_set.create(user=notification_member, roles=[roles.GROUP_EDITOR])
        # add notification type to send out emails
        for membership in self.group.groupmembership_set.all():
            membership.add_notification_types([GroupNotificationType.CONFLICT_RESOLUTION])
            membership.save()
        mail.outbox = []

        # create case
        self.client.force_login(user=self.member)
        response = self.client.post(
            '/api/conflict-resolution/', {
                'group': self.group.id,
                'topic': 'I complain about this user',
                'affected_user': self.affected_member.id,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        case = response.data
        self.assertEqual(case['created_by'], self.member.id)
        self.assertEqual(case['status'], CaseStatus.ONGOING.value)
        self.assertEqual(case['type'], 'conflict_resolution')
        self.assertEqual(case['topic'], 'I complain about this user')
        self.assertEqual(case['group'], self.group.id)
        self.assertEqual(case['affected_user'], self.affected_member.id)
        self.assertEqual(len(case['votings']), 1)
        self.assertLessEqual(parse(case['created_at']), timezone.now())

        voting = case['votings'][0]
        self.assertEqual(voting['participant_count'], 0)

        # check if emails have been sent
        self.assertEqual(len(mail.outbox), 2)
        email_to_affected_user = next(email for email in mail.outbox if email.to[0] == self.affected_member.email)
        email_to_editor = next(email for email in mail.outbox if email.to[0] == notification_member.email)
        self.assertIn('with you', email_to_affected_user.subject)
        self.assertIn('with {}'.format(self.affected_member.display_name), email_to_editor.subject)

        # vote on option
        response = self.client.post(
            '/api/conflict-resolution/votings/{}/vote/'.format(voting['id']),
            make_vote_data(voting['options']),
            format='json'
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
            response = self.client.get('/api/conflict-resolution/{}/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # get conversation
        response = self.client.get('/api/conflict-resolution/{}/conversation/'.format(case['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conversation_id = response.data['id']

        # post message in conversation
        data = {'conversation': conversation_id, 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_vote_can_be_updated_and_deleted(self):
        self.client.force_login(user=self.member)
        case = self.create_case()
        voting = case.votings.first()
        options = voting.options.all()
        option_count = options.count()

        response = self.client.post(
            '/api/conflict-resolution/votings/{}/vote/'.format(voting.id),
            make_vote_data(options, [1] * option_count),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.client.post(
            '/api/conflict-resolution/votings/{}/vote/'.format(voting.id),
            make_vote_data(options, [2] * option_count),
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.assertEqual([v.score for v in Vote.objects.all()], [2] * option_count)

        response = self.client.delete('/api/conflict-resolution/votings/{}/vote/'.format(voting.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        self.assertEqual(Vote.objects.count(), 0)


class TestCaseAPIPermissions(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        settings.CONFLICT_RESOLUTION_ACTIVE_EDITORS_REQUIRED_FOR_CREATION = 1
        self.member = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.affected_member = VerifiedUserFactory()
        self.group = GroupFactory(
            members=[self.member, self.affected_member],
            newcomers=[self.newcomer],
        )

        # effectively disable throttling
        from foodsaving.cases.api import ConflictResolutionThrottle
        ConflictResolutionThrottle.rate = '1000/min'

    def create_case(self, **kwargs):
        return CaseFactory(group=self.group, created_by=self.member, **kwargs)

    def create_case_via_API(self, **kwargs):
        return self.client.post(
            '/api/conflict-resolution/', {
                'group': kwargs.get('group', self.group).id,
                'topic': kwargs.get('topic', 'asdf'),
                'affected_user': kwargs.get('affected_user', self.affected_member).id,
            },
            format='json'
        )

    def vote_via_API(self, voting, data=None):
        return self.client.post(
            '/api/conflict-resolution/votings/{}/vote/'.format(voting.id),
            data or make_vote_data(voting.options.all()),
            format='json'
        )

    def fast_forward_to_voting_expiration(self, voting):
        time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
        return freeze_time(time_when_voting_expires, tick=True)

    def delete_vote_via_API(self, voting):
        return self.client.delete('/api/conflict-resolution/votings/{}/vote/'.format(voting.id))

    def test_cannot_create_case_as_nonmember(self):
        self.client.force_login(user=VerifiedUserFactory())
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_case_as_newcomer(self):
        self.client.force_login(user=self.newcomer)
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_case_with_empty_topic(self):
        self.client.force_login(user=self.member)
        response = self.create_case_via_API(topic='')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

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

    def test_cannot_create_case_about_yourself(self):
        self.client.force_login(user=self.member)
        response = self.create_case_via_API(affected_user=self.member)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_case_in_open_group(self):
        member = VerifiedUserFactory()
        member2 = VerifiedUserFactory()
        open_group = GroupFactory(members=[member, member2], is_open=True)
        self.client.force_login(user=member)
        response = self.create_case_via_API(group=open_group, affected_user=member2)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_case_if_there_are_not_enough_active_editors(self):
        settings.CONFLICT_RESOLUTION_ACTIVE_EDITORS_REQUIRED_FOR_CREATION = 4
        self.client.force_login(user=self.member)
        response = self.create_case_via_API()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_list_cases_as_nonmember(self):
        self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/conflict-resolution/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_list_cases_as_newcomer(self):
        self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/conflict-resolution/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_retrieve_cases_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.get_results('/api/conflict-resolution/{}/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_cases_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/conflict-resolution/{}/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_case_conversation_as_nonmember(self):
        case = self.create_case()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.get_results('/api/conflict-resolution/{}/conversation/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_case_conversation_as_newcomer(self):
        case = self.create_case()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/conflict-resolution/{}/conversation/'.format(case.id))
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

    def test_cannote_change_and_delete_vote_in_cancelled_case(self):
        case = self.create_case(affected_user=self.affected_member)
        voting = case.votings.first()
        vote_for_remove_user(voting=voting, user=case.created_by)

        self.client.force_login(user=case.affected_user)
        response = self.client.post('/api/groups/{}/leave/'.format(case.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(user=case.created_by)
        response = self.vote_via_API(voting)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

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

    def test_removed_member_cannot_access_case(self):
        case = self.create_case(affected_user=self.affected_member)
        vote_for_remove_user(voting=case.latest_voting(), user=case.created_by)
        with self.fast_forward_to_voting_expiration(case.latest_voting()):
            process_expired_votings()

        self.client.force_login(user=self.affected_member)
        # cannot access case
        response = self.get_results('/api/conflict-resolution/{}/'.format(case.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
        # cannot access conversation
        response = self.get_results('/api/conversations/{}/'.format(case.conversation.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
