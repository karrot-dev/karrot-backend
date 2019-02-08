from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupStatus
from foodsaving.places.factories import PlaceFactory
from foodsaving.pickups.models import Feedback, to_range
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory
from foodsaving.pickups.factories import PickupDateFactory, FeedbackFactory


class FeedbackTest(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/feedback/'

        self.member = UserFactory()
        self.collector = UserFactory()
        self.collector2 = UserFactory()
        self.collector3 = UserFactory()
        self.evil_collector = UserFactory()
        self.group = GroupFactory(
            members=[self.member, self.collector, self.evil_collector, self.collector2, self.collector3]
        )
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(
            place=self.place,
            date=to_range(timezone.now() + relativedelta(days=1)),
            collectors=[self.collector, self.collector2, self.collector3],
        )

        # not a member of the group
        self.user = UserFactory()

        # past pickup date
        self.past_pickup = PickupDateFactory(
            place=self.place,
            date=to_range(timezone.now() - relativedelta(days=1)),
            collectors=[self.collector, self.evil_collector, self.collector2, self.collector3],
        )

        # old pickup date with feedback
        self.old_pickup = PickupDateFactory(
            place=self.place,
            date=to_range(timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS + 2)),
            collectors=[
                self.collector3,
            ]
        )
        self.old_feedback = FeedbackFactory(about=self.old_pickup, given_by=self.collector3)

        # create feedback for POST method
        self.feedback_post = {'about': self.past_pickup.id, 'weight': 2, 'comment': 'asfjk'}

        # create feedback for POST method without weight and comment
        self.feedback_without_weight_comment = {
            'about': self.past_pickup.id,
        }

        # create feedback to future pickup
        self.future_feedback_post = {'about': self.pickup.id, 'weight': 2, 'comment': 'asfjk'}

        # create feedback for an old pickup
        self.feedback_for_old_pickup = {'about': self.old_pickup.id, 'weight': 5, 'comment': 'this is long ago'}

        # create feedback for GET method
        self.feedback_get = {'given_by': self.collector, 'about': self.past_pickup, 'weight': 2, 'comment': 'asfjk2'}

        self.feedback_get_2 = {'given_by': self.collector2, 'about': self.past_pickup, 'weight': 2, 'comment': 'asfjk'}

        # create 2 instances of feedback for GET method
        self.feedback = Feedback.objects.create(**self.feedback_get)
        Feedback.objects.create(**self.feedback_get_2)

        self.feedback_url = self.url + str(self.feedback.id) + '/'
        self.old_feedback_url = self.url + str(self.old_feedback.id) + '/'

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

    def test_create_feedback_fails_as_non_collector(self):
        """
        Group Member is not allowed to give feedback when he is not assigned to the pickup.
        """
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'about': ['You aren\'t assigned to the pickup.']})

    def test_create_feedback_works_as_collector(self):
        """
        Editor is allowed to give feedback when he is assigned to the Pickup.
        """
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_feedback_as_newcomer_collector(self):
        """
        Newcomer is allowed to give feedback when he is assigned to the Pickup.
        """
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.past_pickup.add_collector(newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_feedback_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.collector3)
        self.client.post(self.url, self.feedback_post, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_feedback_twice_fails_for_one_pickup(self):
        """
        Collector is not allowed to give feedback more than one time to the Pickup.
        """
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        response = self.client.post(self.url, self.feedback_post, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['The fields about, given_by must make a unique set.']})

    def test_create_feedback_fails_for_old_pickup(self):
        """
        Collector is not allowed to give feedback for old Pickups.
        """
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, self.feedback_for_old_pickup, format='json')
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
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, {k: v for (k, v) in self.feedback_post.items() if k != 'weight'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['weight'])

    def test_create_feedback_without_comment(self):
        """
        Comment field can be empty
        """
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, {k: v for (k, v) in self.feedback_post.items() if k != 'comment'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['comment'], '')

    def test_weight_and_comment_is_null_fails(self):
        """
        Both comment and weight cannot be empty
        """
        self.client.force_login(user=self.collector3)
        response = self.client.post(self.url, self.feedback_without_weight_comment, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

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
        pickup_ids = set(f['about'] for f in feedback)
        self.assertEqual(len(response.data['pickups']), len(pickup_ids))
        self.assertEqual(set(p['id'] for p in response.data['pickups']), pickup_ids)

    def test_list_feedback_works_as_collector(self):
        """
        Collector is allowed to see list of feedback
        """
        self.client.force_login(user=self.collector)
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

    def test_retrieve_feedback_works_as_collector(self):
        """
        Collector is allowed to see list of feedback
        """
        self.client.force_login(user=self.collector)
        response = self.get_results(self.feedback_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_create_future_feedback_fails_as_collector(self):
        """
        Collector is NOT allowed to leave feedback for future pickup
        """
        self.client.force_login(user=self.collector3)
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

    def test_patch_feedback_fails_as_evil_collector(self):
        """
        A collector is not allowed to change feedback if he didn't created it
        """
        self.client.force_login(user=self.evil_collector)
        response = self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_feedback_works_as_collector(self):
        """
        Collector is allowed to change feedback
        """
        self.client.force_login(user=self.collector)
        response = self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weight'], 3)

    def test_patch_feedback_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.collector)
        self.client.patch(self.feedback_url, {'weight': 3}, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_patch_weight_to_negative_value_fails(self):
        """
        Collector cannot change weight to negative value
        """
        self.client.force_login(user=self.collector)
        response = self.client.patch(self.feedback_url, {'weight': -1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_feedback_fails_if_pickup_too_old(self):
        self.client.force_login(user=self.collector3)
        response = self.client.patch(self.old_feedback_url, {'weight': 499}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(
            response.data['detail'],
            'You can\'t give feedback for pickups more than {} days ago.'.format(settings.FEEDBACK_POSSIBLE_DAYS)
        )

    def test_patch_feedback_to_remove_weight(self):
        self.client.force_login(user=self.collector)
        response = self.client.patch(self.feedback_url, {'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['weight'], None)

    def test_patch_feedback_to_remove_weight_fails_if_comment_is_empty(self):
        self.client.force_login(user=self.collector)
        self.feedback.comment = ''
        self.feedback.save()
        response = self.client.patch(self.feedback_url, {'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

    def test_patch_feedback_to_remove_comment(self):
        self.client.force_login(user=self.collector)
        response = self.client.patch(self.feedback_url, {'comment': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['comment'], '')

    def test_patch_feedback_to_remove_comment_fails_if_weight_is_empty(self):
        self.client.force_login(user=self.collector)
        self.feedback.weight = None
        self.feedback.save()
        response = self.client.patch(self.feedback_url, {'comment': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})

    def test_patch_feedback_to_remove_comment_and_weight_fails(self):
        self.client.force_login(user=self.collector)
        response = self.client.patch(self.feedback_url, {'comment': '', 'weight': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'non_field_errors': ['Both comment and weight cannot be blank.']})
