from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.issues.factories import IssueFactory, vote_for_remove_user, vote_for_no_change
from karrot.issues.models import Vote, IssueStatus
from karrot.issues.tasks import process_expired_votings
from karrot.groups import roles
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupNotificationType
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import VerifiedUserFactory


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
        self.group = GroupFactory(members=[self.member], newcomers=[self.affected_member])

        # effectively disable throttling
        from karrot.issues.api import IssuesCreateThrottle
        IssuesCreateThrottle.rate = '1000/min'

    def create_issue(self, **kwargs):
        return IssueFactory(group=self.group, created_by=self.member, **kwargs)

    def test_create_conflict_resolution_and_vote(self):
        # add another editor
        notification_member = VerifiedUserFactory()
        self.group.groupmembership_set.create(
            user=notification_member,
            roles=[roles.GROUP_EDITOR],
            notification_types=[GroupNotificationType.CONFLICT_RESOLUTION]
        )
        # add notification type to send out emails
        self.group.groupmembership_set.filter(user=self.member
                                              ).update(notification_types=[GroupNotificationType.CONFLICT_RESOLUTION])
        mail.outbox = []

        # create issue
        self.client.force_login(user=self.member)
        response = self.client.post(
            '/api/issues/', {
                'group': self.group.id,
                'topic': 'I complain about this user',
                'affected_user': self.affected_member.id,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        issue = response.data
        self.assertEqual(issue['created_by'], self.member.id)
        self.assertEqual(issue['status'], IssueStatus.ONGOING.value)
        self.assertEqual(issue['type'], 'conflict_resolution')
        self.assertEqual(issue['topic'], 'I complain about this user')
        self.assertEqual(issue['group'], self.group.id)
        self.assertEqual(issue['affected_user'], self.affected_member.id)
        self.assertEqual(len(issue['votings']), 1)
        self.assertLessEqual(parse(issue['created_at']), timezone.now())

        voting = issue['votings'][0]
        self.assertEqual(voting['participant_count'], 0)

        # check if emails have been sent
        self.assertEqual(len(mail.outbox), 2)
        email_to_affected_user = next(email for email in mail.outbox if email.to[0] == self.affected_member.email)
        email_to_editor = next(email for email in mail.outbox if email.to[0] == notification_member.email)
        self.assertIn('about you', email_to_affected_user.subject)
        self.assertIn('about {}'.format(self.affected_member.display_name), email_to_editor.subject)

        # vote on option
        response = self.client.post(
            '/api/issues/{}/vote/'.format(issue['id']), make_vote_data(voting['options']), format='json'
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
            response = self.client.get('/api/issues/{}/'.format(issue['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # get conversation
        response = self.client.get('/api/issues/{}/conversation/'.format(issue['id']))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conversation_id = response.data['id']

        # post message in conversation
        data = {'conversation': conversation_id, 'content': 'a nice message'}
        response = self.client.post('/api/messages/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_vote_can_be_updated_and_deleted(self):
        self.client.force_login(user=self.member)
        issue = self.create_issue()
        voting = issue.latest_voting()
        options = voting.options.all()
        option_count = options.count()

        response = self.client.post(
            '/api/issues/{}/vote/'.format(issue.id), make_vote_data(options, [1] * option_count), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.client.post(
            '/api/issues/{}/vote/'.format(issue.id), make_vote_data(options, [2] * option_count), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.assertEqual([v.score for v in Vote.objects.all()], [2] * option_count)

        response = self.client.delete('/api/issues/{}/vote/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        self.assertEqual(Vote.objects.count(), 0)

    def test_list_issues_efficiently(self):
        self.create_issue()
        self.create_issue()
        self.create_issue()

        self.client.force_login(user=self.member)
        with self.assertNumQueries(6):
            response = self.get_results('/api/issues/', {'group': self.group.id}, format='json')
        self.assertEqual(len(response.data), 3)


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
        from karrot.issues.api import IssuesCreateThrottle
        IssuesCreateThrottle.rate = '1000/min'

    def create_issue(self, **kwargs):
        return IssueFactory(group=self.group, created_by=self.member, **kwargs)

    def create_issue_via_API(self, **kwargs):
        return self.client.post(
            '/api/issues/', {
                'group': kwargs.get('group', self.group).id,
                'topic': kwargs.get('topic', 'asdf'),
                'affected_user': kwargs.get('affected_user', self.affected_member).id,
            },
            format='json'
        )

    def vote_via_API(self, issue, data=None):
        voting = issue.latest_voting()
        return self.client.post(
            '/api/issues/{}/vote/'.format(issue.id), data or make_vote_data(voting.options.all()), format='json'
        )

    def fast_forward_to_voting_expiration(self, voting):
        time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
        return freeze_time(time_when_voting_expires, tick=True)

    def delete_vote_via_API(self, issue):
        return self.client.delete('/api/issues/{}/vote/'.format(issue.id))

    def test_cannot_create_issue_as_nonmember(self):
        self.client.force_login(user=VerifiedUserFactory())
        response = self.create_issue_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_issue_as_newcomer(self):
        self.client.force_login(user=self.newcomer)
        response = self.create_issue_via_API()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_issue_with_empty_topic(self):
        self.client.force_login(user=self.member)
        response = self.create_issue_via_API(topic='')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_twice_for_same_person(self):
        self.client.force_login(user=self.member)
        response = self.create_issue_via_API()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        response = self.create_issue_via_API()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_issue_about_nonmember(self):
        self.client.force_login(user=self.member)
        response = self.create_issue_via_API(affected_user=VerifiedUserFactory())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_create_issue_about_yourself(self):
        self.client.force_login(user=self.member)
        response = self.create_issue_via_API(affected_user=self.member)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_can_create_issue_in_open_group(self):
        member = VerifiedUserFactory()
        member2 = VerifiedUserFactory()
        open_group = GroupFactory(members=[member, member2], is_open=True)
        self.client.force_login(user=member)
        response = self.create_issue_via_API(group=open_group, affected_user=member2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_create_issue_if_there_are_not_enough_active_editors(self):
        settings.CONFLICT_RESOLUTION_ACTIVE_EDITORS_REQUIRED_FOR_CREATION = 4
        self.client.force_login(user=self.member)
        response = self.create_issue_via_API()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_list_issues_as_nonmember(self):
        self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/issues/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_list_issues_as_newcomer(self):
        self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/issues/?group={}'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_cannot_retrieve_issues_as_nonmember(self):
        issue = self.create_issue()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.get_results('/api/issues/{}/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_issues_as_newcomer(self):
        issue = self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/issues/{}/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_issue_conversation_as_nonmember(self):
        issue = self.create_issue()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.get_results('/api/issues/{}/conversation/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_retrieve_issue_conversation_as_newcomer(self):
        issue = self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.get_results('/api/issues/{}/conversation/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_as_nonmember(self):
        issue = self.create_issue()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_as_newcomer(self):
        issue = self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_nonmember(self):
        issue = self.create_issue()
        self.client.force_login(user=VerifiedUserFactory())
        response = self.delete_vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_delete_vote_as_newcomer(self):
        issue = self.create_issue()
        self.client.force_login(user=self.newcomer)
        response = self.delete_vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_cannot_vote_in_expired_voting(self):
        issue = self.create_issue()
        voting = issue.votings.first()
        vote_for_no_change(voting=voting, user=self.affected_member)
        self.client.force_login(user=self.member)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_change_vote_in_decided_issue(self):
        issue = self.create_issue()
        voting = issue.votings.first()
        vote_for_no_change(voting=voting, user=self.member)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_delete_vote_in_decided_issue(self):
        issue = self.create_issue()
        voting = issue.votings.first()
        vote_for_no_change(voting=voting, user=self.member)
        with self.fast_forward_to_voting_expiration(voting):
            process_expired_votings()
            response = self.delete_vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannote_change_and_delete_vote_in_cancelled_issue(self):
        issue = self.create_issue(affected_user=self.affected_member)
        voting = issue.votings.first()
        vote_for_remove_user(voting=voting, user=issue.created_by)

        self.client.force_login(user=issue.affected_user)
        response = self.client.post('/api/groups/{}/leave/'.format(issue.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(user=issue.created_by)
        response = self.vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

        response = self.delete_vote_via_API(issue)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_must_provide_score_for_all_options_in_voting(self):
        issue = self.create_issue()
        voting = issue.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(issue, data=[{'option': voting.options.first().id, 'score': 1}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual('You need to provide a score for all options', response.data['non_field_errors'][0])

    def test_cannot_provide_score_for_options_in_other_voting(self):
        issue = self.create_issue()
        issue2 = self.create_issue()
        voting2 = issue2.votings.first()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(issue, data=[{'option': voting2.options.first().id, 'score': 1}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual('Provided option is not part of this voting', response.data[0]['option'][0])

    def test_cannot_provide_single_vote(self):
        issue = self.create_issue()
        voting = issue.latest_voting()
        self.client.force_login(user=self.member)
        response = self.vote_via_API(issue, data={'option': voting.options.first().id, 'score': 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_removed_member_cannot_access_issue(self):
        issue = self.create_issue(affected_user=self.affected_member)
        vote_for_remove_user(voting=issue.latest_voting(), user=issue.created_by)
        with self.fast_forward_to_voting_expiration(issue.latest_voting()):
            process_expired_votings()

        self.client.force_login(user=self.affected_member)
        # cannot access issue
        response = self.get_results('/api/issues/{}/'.format(issue.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
        # cannot access conversation
        response = self.get_results('/api/conversations/{}/'.format(issue.conversation.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
