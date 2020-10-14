from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupStatus
from karrot.places.factories import PlaceFactory
from karrot.activities.models import Feedback, to_range
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory
from karrot.activities.factories import ActivityFactory, FeedbackFactory, ActivityTypeFactory


class FeedbackTest(APITestCase, ExtractPaginationMixin):
    @classmethod
    def setUpTestData(cls):
        """ This method runs once before tests in this class """
        cls.url = '/api/feedback/'

        cls.member = UserFactory()
        cls.participant = UserFactory()
        cls.participant2 = UserFactory()
        cls.participant3 = UserFactory()
        cls.evil_participant = UserFactory()
        cls.group = GroupFactory(
            members=[cls.member, cls.participant, cls.evil_participant, cls.participant2, cls.participant3]
        )
        cls.place = PlaceFactory(group=cls.group)
        cls.activity = ActivityFactory(
            place=cls.place,
            date=to_range(timezone.now() + relativedelta(days=1)),
            participants=[cls.participant, cls.participant2, cls.participant3],
        )

        activity_type_without_feedback_weight = ActivityTypeFactory(
            group=cls.group,
            has_feedback=True,
            has_feedback_weight=False,
        )

        activity_type_without_feedback = ActivityTypeFactory(
            group=cls.group,
            has_feedback=False,
            has_feedback_weight=False,
        )

        # not a member of the group
        cls.user = UserFactory()

        # past activity
        cls.past_activity = ActivityFactory(
            place=cls.place,
            date=to_range(timezone.now() - relativedelta(days=1)),
            participants=[cls.participant, cls.evil_participant, cls.participant2, cls.participant3],
        )

        # old activity with feedback
        cls.old_activity = ActivityFactory(
            place=cls.place,
            date=to_range(timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS + 2)),
            participants=[
                cls.participant3,
            ]
        )
        cls.old_feedback = FeedbackFactory(about=cls.old_activity, given_by=cls.participant3)

        # activity for type that doesn't accept feedback weight
        cls.activity_without_feedback_weight = ActivityFactory(
            typus=activity_type_without_feedback_weight,
            place=cls.place,
            date=to_range(timezone.now() - relativedelta(days=1)),
            participants=[cls.participant, cls.participant2, cls.participant3],
        )

        # activity for type that doesn't accept feedback at all
        cls.activity_without_feedback = ActivityFactory(
            typus=activity_type_without_feedback,
            place=cls.place,
            date=to_range(timezone.now() - relativedelta(days=1)),
            participants=[cls.participant, cls.participant2, cls.participant3],
        )

        # create feedback for POST method
        cls.feedback_post = {'about': cls.past_activity.id, 'weight': 2, 'comment': 'asfjk'}

        # create feedback for POST method without weight and comment
        cls.feedback_without_weight_comment = {
            'about': cls.past_activity.id,
        }

        # create feedback to future activity
        cls.future_feedback_post = {'about': cls.activity.id, 'weight': 2, 'comment': 'asfjk'}

        # create feedback for an old activity
        cls.feedback_for_old_activity = {'about': cls.old_activity.id, 'weight': 5, 'comment': 'this is long ago'}

        # create feedback for GET method
        cls.feedback_get = {'given_by': cls.participant, 'about': cls.past_activity, 'weight': 2, 'comment': 'asfjk2'}

        cls.feedback_get_2 = {
            'given_by': cls.participant2,
            'about': cls.past_activity,
            'weight': 2,
            'comment': 'asfjk'
        }

        # create 2 instances of feedback for GET method
        cls.feedback = Feedback.objects.create(**cls.feedback_get)
        Feedback.objects.create(**cls.feedback_get_2)

        cls.feedback_url = cls.url + str(cls.feedback.id) + '/'
        cls.old_feedback_url = cls.url + str(cls.old_feedback.id) + '/'

    def setUp(self):
        """ This method runs before each test. Refresh some data that gets modified in test cases. """
        self.group.refresh_from_db()
        self.feedback.refresh_from_db()

    def test_create_feedback_fails_as_non_user(self):
        """
        Non-User is not allowed to give feedback.
        """
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_feedback_fails_as_non_group_member(self):
        """
        User is not allowed to give feedback when not a member of the place's group.
        """
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['You are not member of the place\'s group.']})

    def test_create_feedback_fails_as_non_participant(self):
        """
        Group Member is not allowed to give feedback when he is not assigned to the activity.
        """
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['You aren\'t assigned to the pickup.']})

    def test_create_feedback_works_as_participant(self):
        """
        Editor is allowed to give feedback when he is assigned to the Activity.
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_feedback_as_newcomer_participant(self):
        """
        Newcomer is allowed to give feedback when he is assigned to the Activity.
        """
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.past_activity.add_participant(newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_feedback_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.participant3)
        self.client.post(self.url, self.feedback_post, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_feedback_twice_fails_for_one_activity(self):
        """
        Participant is not allowed to give feedback more than one time to the Activity.
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['The fields about, given_by must make a unique set.']})

    def test_create_feedback_fails_for_old_activity(self):
        """
        Participant is not allowed to give feedback for old Activities.
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, self.feedback_for_old_activity, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(
            response.data, {
                'about': [
                    'You can\'t give feedback for pickups more than {} days ago.'.format(
                        settings.FEEDBACK_POSSIBLE_DAYS
                    )
                ]
            }
        )

    def test_create_feedback_without_weight(self):
        """
        Weight field can be empty
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, {k: v for (k, v) in self.feedback_post.items() if k != 'weight'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['weight'])

    def test_create_feedback_without_comment(self):
        """
        Comment field can be empty
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, {k: v for (k, v) in self.feedback_post.items() if k != 'comment'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['comment'], '')

    def test_weight_and_comment_is_null_fails(self):
        """
        Both comment and weight cannot be empty
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, self.feedback_without_weight_comment, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

    def test_weight_for_activity_that_does_not_accept_weight(self):
        self.maxDiff = None
        self.client.force_login(user=self.participant3)
        response = self.client.post(
            self.url, {
                'about': self.activity_without_feedback_weight.id,
                'comment': 'hello',
                'weight': 200,
            },
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(
            response.data, {
                'non_field_errors': [
                    'You cannot give weight feedback to an activity of type {}.'.format(
                        self.activity_without_feedback_weight.typus.name
                    )
                ]
            }
        )

    def test_weight_for_activity_that_does_not_accept_feedback(self):
        self.maxDiff = None
        self.client.force_login(user=self.participant3)
        response = self.client.post(
            self.url, {
                'about': self.activity_without_feedback.id,
                'comment': 'hello',
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(
            response.data, {
                'non_field_errors': [
                    'You cannot give feedback to an activity of type {}.'.format(
                        self.activity_without_feedback.typus.name
                    )
                ]
            }
        )

    def test_list_feedback_fails_as_non_user(self):
        """
        Non-User is NOT allowed to see list of feedback
        """
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_feedback_works_as_non_group_member(self):
        """
        Non-Member doesn't see feedback but an empty list
        """
        self.client.force_login(user=self.user)
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['feedback']), 0)

    def test_list_feedback_works_as_group_member(self):
        """
        Member is allowed to see list of feedback
        """
        self.client.force_login(user=self.member)
        with self.assertNumQueries(4):
            response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        feedback = response.data['feedback']
        self.assertEqual(len(feedback), 3)

        # check related data
        activity_ids = set(f['about'] for f in feedback)
        self.assertEqual(len(response.data['activities']), len(activity_ids))
        self.assertEqual(set(p['id'] for p in response.data['activities']), activity_ids)

    def test_export_feedback(self):
        self.client.force_login(user=self.member)
        with self.assertNumQueries(2):
            response = self.get_results(self.url + 'export/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        feedback = response.data[0]

        # converts dates into group timezone
        self.assertFalse(feedback['created_at'].endswith('Z'))

        # includes activity
        self.assertFalse(feedback['about_date'].endswith('Z'))

        # includes place id
        self.assertIn('about_place', feedback)

    def test_list_feedback_works_as_participant(self):
        """
        Participant is allowed to see list of feedback
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['feedback']), 3)

    def test_retrieve_feedback_fails_as_non_user(self):
        """
        Non-User is NOT allowed to see single feedback
        """
        response = self.get_results(self.feedback_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_retrieve_feedback_fails_as_non_group_member(self):
        """
        Non-Member is NOT allowed to see single feedback
        """
        self.client.force_login(user=self.user)
        response = self.get_results(self.feedback_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_retrieve_feedback_works_as_group_member(self):
        """
        Member is allowed to see single feedback
        """
        self.client.force_login(user=self.member)
        response = self.get_results(self.feedback_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_retrieve_feedback_works_as_participant(self):
        """
        Participant is allowed to see list of feedback
        """
        self.client.force_login(user=self.participant)
        response = self.get_results(self.feedback_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_create_future_feedback_fails_as_participant(self):
        """
        Participant is NOT allowed to leave feedback for future activity
        """
        self.client.force_login(user=self.participant3)
        response = self.client.post(self.url, self.future_feedback_post)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['The pickup is not done yet']})

    def test_patch_feedback_fails_as_non_user(self):
        """
        Non-user is not allowed to change feedback
        """
        response = self.client.patch(self.feedback_url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_feedback_fails_as_user(self):
        """
        User is not allowed to change feedback
        """
        self.client.force_login(user=self.user)
        response = self.client.patch(self.feedback_url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_patch_feedback_fails_as_group_member(self):
        """
        Group member is not allowed to change feedback
        """
        self.client.force_login(user=self.member)
        response = self.client.patch(self.feedback_url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_feedback_fails_as_evil_participant(self):
        """
        A participant is not allowed to change feedback if he didn't created it
        """
        self.client.force_login(user=self.evil_participant)
        response = self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_feedback_works_as_participant(self):
        """
        Participant is allowed to change feedback
        """
        self.client.force_login(user=self.participant)
        response = self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weight'], 3)

    def test_patch_feedback_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.participant)
        self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_patch_weight_to_negative_value_fails(self):
        """
        Participant cannot change weight to negative value
        """
        self.client.force_login(user=self.participant)
        response = self.client.patch(self.feedback_url, {'weight': -1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_feedback_fails_if_activity_too_old(self):
        self.client.force_login(user=self.participant3)
        response = self.client.patch(self.old_feedback_url, {'weight': 499}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(
            response.data['detail'],
            'You can\'t give feedback for pickups more than {} days ago.'.format(settings.FEEDBACK_POSSIBLE_DAYS)
        )

    def test_patch_feedback_to_remove_weight(self):
        self.client.force_login(user=self.participant)
        response = self.client.patch(self.feedback_url, {'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weight'], None)

    def test_patch_feedback_to_remove_weight_fails_if_comment_is_empty(self):
        self.client.force_login(user=self.participant)
        self.feedback.comment = ''
        self.feedback.save()
        response = self.client.patch(self.feedback_url, {'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

    def test_patch_feedback_to_remove_comment(self):
        self.client.force_login(user=self.participant)
        response = self.client.patch(self.feedback_url, {'comment': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['comment'], '')

    def test_patch_feedback_to_remove_comment_fails_if_weight_is_empty(self):
        self.client.force_login(user=self.participant)
        self.feedback.weight = None
        self.feedback.save()
        response = self.client.patch(self.feedback_url, {'comment': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

    def test_patch_feedback_to_remove_comment_and_weight_fails(self):
        self.client.force_login(user=self.participant)
        response = self.client.patch(self.feedback_url, {'comment': '', 'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})
