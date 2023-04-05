from datetime import timedelta
from unittest.mock import ANY

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.base.base_models import CustomDateTimeTZRange
from karrot.conversations.models import ConversationNotificationStatus
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupStatus
from karrot.activities.factories import ActivityFactory, ActivityTypeFactory
from karrot.activities.models import to_range, ActivityParticipant
from karrot.groups.roles import GROUP_MEMBER
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin, pluck
from karrot.users.factories import UserFactory

APPROVED = 'approved'


class TestActivitiesAPI(APITestCase, ExtractPaginationMixin):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/api/activities/'

        # default set
        participant_types = [
            {
                'role': 'member',
                'max_participants': 5,
                'description': '',
            },
        ]

        # activity for group with one member and one place
        cls.member = UserFactory()
        cls.second_member = UserFactory()
        cls.group = GroupFactory(members=[cls.member, cls.second_member])
        cls.place = PlaceFactory(group=cls.group)
        cls.activity_type = ActivityTypeFactory(group=cls.group)
        cls.archived_activity_type = ActivityTypeFactory(group=cls.group, status='archived')
        cls.activity = ActivityFactory(activity_type=cls.activity_type, place=cls.place)
        cls.activity_url = cls.url + str(cls.activity.id) + '/'
        cls.join_url = cls.activity_url + 'add/'
        cls.leave_url = cls.activity_url + 'remove/'
        cls.conversation_url = cls.activity_url + 'conversation/'
        cls.dismiss_feedback_url = cls.activity_url + 'dismiss_feedback/'

        # not a member of the group
        cls.user = UserFactory()

        # another activity for above place
        cls.activity_data = {
            'activity_type': cls.activity_type.id,
            'date': to_range(timezone.now() + relativedelta(days=2)).as_list(),
            'place': cls.place.id
        }
        cls.activity_create_data = {
            **cls.activity_data,
            'participant_types': participant_types,
        }

        # past activity
        cls.past_activity_data = {
            'activity_type': cls.activity_type.id,
            'date': to_range(timezone.now() - relativedelta(days=1)).as_list(),
            'place': cls.place.id
        }
        cls.past_activity_create_data = {
            **cls.past_activity_data,
            'participant_types': participant_types,
        }
        cls.past_activity = ActivityFactory(
            activity_type=cls.activity_type, place=cls.place, date=to_range(timezone.now() - relativedelta(days=1))
        )
        cls.past_activity_url = cls.url + str(cls.past_activity.id) + '/'
        cls.past_join_url = cls.past_activity_url + 'add/'
        cls.past_leave_url = cls.past_activity_url + 'remove/'
        cls.past_dismiss_feedback_url = cls.past_activity_url + 'dismiss_feedback/'

    def setUp(self):
        self.group.refresh_from_db()

    def test_create_activity(self):
        response = self.client.post(self.url, self.activity_create_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_activity_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.activity_create_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_activity_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.activity_create_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_activity_for_archived_type_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.post(
            self.url, {
                **self.activity_create_data,
                'activity_type': self.archived_activity_type.id,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_create_activity_as_group_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.url, self.activity_create_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_past_activity_date_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.past_activity_create_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_create_activity_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.activity_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_activities(self):
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_activities_as_user(self):
        self.client.force_login(user=self.user)
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_list_activities_as_group_member(self):
        self.client.force_login(user=self.member)
        with self.assertNumQueries(5):
            response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_activities(self):
        response = self.client.get(self.activity_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_retrieve_activities_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.activity_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_retrieve_activities_as_group_member(self):
        self.client.force_login(user=self.member)
        with self.assertNumQueries(5):
            response = self.client.get(self.activity_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_patch_activity(self):
        response = self.client.patch(self.activity_url, self.activity_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_activity_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.patch(self.activity_url, self.activity_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_patch_activity_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.activity_url, self.activity_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_patch_activity_as_group_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.patch(self.activity_url, self.activity_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_patch_max_participants_to_negative_value_fails(self):
        self.client.force_login(user=self.member)
        id = self.activity.participant_types.first().id
        response = self.client.patch(
            self.activity_url, {'participant_types': {
                'id': id,
                'max_participants': -1
            }}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_past_activity_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.past_activity_url, self.activity_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.activity_url, {'description': 'woo'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_join_activity(self):
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_join_activity_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_join_activity_as_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # should have access to chat
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_activity_order_by_sign_up(self):
        self.client.force_login(user=self.second_member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(user=self.member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        participant_order = [self.second_member.id, self.member.id]
        response = self.client.get(self.activity_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(pluck(response.data['participants'], 'user'), participant_order)

        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        activity = next(p for p in response.data if p['id'] == self.activity.id)
        self.assertEqual(pluck(activity['participants'], 'user'), participant_order)

        # reverse order
        participant = self.activity.activityparticipant_set.earliest('created_at')
        participant.created_at = timezone.now()
        participant.save()
        participant_order = [self.member.id, self.second_member.id]

        response = self.client.get(self.activity_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(pluck(response.data['participants'], 'user'), participant_order)

        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        activity = next(p for p in response.data if p['id'] == self.activity.id)
        self.assertEqual(pluck(activity['participants'], 'user'), participant_order)

    def test_join_activity_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_join_activity_as_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.join_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_join_activity_without_max_participants_as_member(self):
        self.client.force_login(user=self.member)
        activity = ActivityFactory(place=self.place, participant_types=[{'role': GROUP_MEMBER, 'max_participants': 5}])
        response = self.client.post('/api/activities/{}/add/'.format(activity.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_join_full_activity_fails(self):
        self.client.force_login(user=self.member)
        self.activity.participant_types.update(max_participants=1)
        self.activity.save()
        u2 = UserFactory()
        self.group.add_member(u2)
        self.activity.add_participant(u2)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['detail'], 'Activity is already full.')

    def test_join_started_but_not_finished_activity(self):
        activity = ActivityFactory(
            place=self.place,
            date=to_range(timezone.now(), hours=4),
        )
        # jump to 5 minutes after it starts
        with freeze_time(activity.date.start + relativedelta(minutes=5), tick=True):
            self.client.force_login(user=self.member)
            response = self.client.post('/api/activities/{}/add/'.format(activity.id))
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_join_past_activity_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.past_join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_leave_activity(self):
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_leave_activity_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_leave_activity_as_member(self):
        self.client.force_login(user=self.member)
        self.activity.add_participant(self.member)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # should be removed from chat
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['notifications'], ConversationNotificationStatus.NONE.value)

    def test_leave_activity_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.activity.add_participant(newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_leave_activity_activates_group(self):
        self.client.force_login(user=self.member)
        self.activity.add_participant(self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.leave_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_leave_past_activity_fails(self):
        self.client.force_login(user=self.member)
        self.past_activity.add_participant(self.member)
        response = self.client.post(self.past_leave_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_dismiss_feedback(self):
        response = self.client.post(self.dismiss_feedback_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_dismiss_feedback_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.dismiss_feedback_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_dismiss_feedback_as_member(self):
        self.client.force_login(user=self.member)
        self.past_activity.add_participant(self.member)
        response = self.client.post(self.past_dismiss_feedback_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_dismiss_feedback_for_upcoming_activity_as_member(self):
        self.client.force_login(user=self.member)
        self.activity.add_participant(self.member)
        response = self.client.post(self.dismiss_feedback_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_dismiss_feedback_not_participated_as_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.past_dismiss_feedback_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_get_conversation_as_participant(self):
        self.client.force_login(user=self.member)
        self.activity.add_participant(self.member)

        # can get via activity
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.member.id, response.data['participants'])
        self.assertEqual(response.data['type'], 'activity')

        # can get via conversations
        conversation_id = self.activity.conversation.id
        response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # can write a message
        response = self.client.post('/api/messages/', {
            'conversation': response.data['id'],
            'content': 'hey',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_can_participate_in_conversation_as_nonparticipant(self):
        self.client.force_login(user=self.member)

        # can get via activity
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # can get via conversation
        conversation_id = self.activity.conversation.id
        response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # can write a message
        response = self.client.post('/api/messages/', {
            'conversation': response.data['id'],
            'content': 'hey',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_get_conversation_as_nonmember(self):
        self.client.force_login(user=self.user)

        # cannot get via activity
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # cannot get via conversation info
        conversation_id = self.activity.conversation.id
        response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # cannot write a message
        conversation_id = self.activity.conversation.id
        response = self.client.post('/api/messages/', {
            'conversation': conversation_id,
            'content': 'hey',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['detail'], 'You are not in this conversation')

    def test_patch_date(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        end = timezone.now() + timedelta(hours=2)
        response = self.client.patch(
            self.activity_url, {
                'date': [start, end],
                'has_duration': True,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.date, CustomDateTimeTZRange(start, end))

    def test_remove_duration_resets_end_date(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        end = timezone.now() + timedelta(hours=2)
        response = self.client.patch(self.activity_url, {'date': [start, end], 'has_duration': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = self.client.patch(self.activity_url, {'has_duration': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.activity.refresh_from_db()
        self.assertEqual(self.activity.date, CustomDateTimeTZRange(start, start + timedelta(minutes=30)))

    def test_cannot_set_empty_duration(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        response = self.client.patch(self.activity_url, {'date': [start, start], 'has_duration': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_start_date_only_uses_default_duration(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        response = self.client.patch(
            self.activity_url, {
                'date': [start],
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.date.end, start + timedelta(minutes=30))

    def test_patch_date_with_single_date_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.activity_url, {
                'date': timezone.now(),
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_end_date_only_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.activity_url, {
                'date': [None, timezone.now()],
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_mark_as_done(self):
        # This is just temporarily - if we need this feature at some point, we should enable it
        # Make sure to create history entries!
        self.client.force_login(user=self.member)
        self.assertEqual(self.activity.is_done, False)
        response = self.client.patch(self.activity_url, {'is_done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.activity.refresh_from_db()
        self.assertFalse(self.activity.is_done, False)

    def test_export_ics_logged_out(self):
        response = self.client.get('/api/activities/{id}/ics/'.format(id=self.activity.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_export_ics_not_group_member(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/activities/{id}/ics/'.format(id=self.activity.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_export_ics_logged_in(self):
        self.client.force_login(user=self.member)
        # first, join the activity to make sure it has an attendee
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = self.client.get('/api/activities/{id}/ics/'.format(id=self.activity.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEquals(response.data['status'], 'CONFIRMED')

    def test_export_ics_disabled_activity(self):
        self.client.force_login(user=self.member)
        self.activity.is_disabled = True
        self.activity.save()
        response = self.client.get('/api/activities/{id}/ics/'.format(id=self.activity.id))
        # disabled activities are still visible
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEquals(response.data['status'], 'CANCELLED')

    def test_export_ics_activities_logged_out(self):
        response = self.get_results('/api/activities/ics/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)

    def test_export_ics_activities_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.get_results('/api/activities/ics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_export_ics_activities_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results('/api/activities/ics/', {'place': self.place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_export_ics_activities_group(self):
        self.client.force_login(user=self.member)
        response = self.get_results('/api/activities/ics/', {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class TestActivitiesWithParticipantTypeAPI(APITestCase):
    def setUp(self):
        self.member = UserFactory()
        self.other_member = UserFactory()
        self.group = GroupFactory(members=[self.member, self.other_member])
        self.place = PlaceFactory(group=self.group, status='active')
        self.approved_member = UserFactory()
        self.group.groupmembership_set.create(
            user=self.approved_member,
            roles=[GROUP_MEMBER, APPROVED],
        )
        self.activity = ActivityFactory(
            place=self.place,
            participant_types=[
                {
                    'role': GROUP_MEMBER,
                    'max_participants': 1,
                },
                {
                    'role': APPROVED,
                    'max_participants': 10,
                },
            ]
        )

    def test_cannot_join_open_slot_if_none_available(self):
        activity = ActivityFactory(
            place=self.place, participant_types=[
                {
                    'role': APPROVED,
                    'max_participants': 10,
                },
            ]
        )
        self.client.force_login(user=self.member)
        response = self.client.post('/api/activities/{}/add/'.format(activity.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_join_as_member_participant(self):
        pt_member = self.activity.participant_types.get(role=GROUP_MEMBER)
        pt_approved = self.activity.participant_types.get(role=APPROVED)
        self.activity.add_participant(self.approved_member, participant_type=pt_approved)
        self.client.force_login(user=self.member)
        response = self.client.post(
            '/api/activities/{}/add/'.format(self.activity.id), {'participant_type': pt_member.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        participant = ActivityParticipant.objects.get(activity=self.activity, user=self.member)
        self.assertEqual(participant.participant_type.role, GROUP_MEMBER)

    def test_cannot_join_as_participant_without_type_if_full(self):
        pt_member = self.activity.participant_types.get(role=GROUP_MEMBER)
        self.activity.add_participant(self.member, participant_type=pt_member)
        self.client.force_login(user=self.other_member)
        response = self.client.post('/api/activities/{}/add/'.format(self.activity.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_can_join_with_participant_type(self):
        self.client.force_login(user=self.approved_member)
        pt_approved = self.activity.participant_types.get(role=APPROVED)
        response = self.client.post(
            '/api/activities/{}/add/'.format(self.activity.id), {'participant_type': pt_approved.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        participant = ActivityParticipant.objects.get(activity=self.activity, user=self.approved_member)
        self.assertEqual(participant.participant_type.role, APPROVED)

    def test_cannot_join_if_missing_role(self):
        self.client.force_login(user=self.member)
        response = self.client.post('/api/activities/{}/add/'.format(self.activity.id), {'role': APPROVED})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_participants_api(self):
        pt_member = self.activity.participant_types.get(role=GROUP_MEMBER)
        pt_approved = self.activity.participant_types.get(role=APPROVED)
        self.activity.add_participant(self.member, participant_type=pt_member)
        self.activity.add_participant(self.approved_member, participant_type=pt_approved)
        self.client.force_login(user=self.member)
        response = self.client.get('/api/activities/{}/'.format(self.activity.id))

        self.assertEqual(
            response.data['participants'], [{
                'user': self.member.id,
                'participant_type': ANY,
                'created_at': ANY,
            }, {
                'user': self.approved_member.id,
                'participant_type': ANY,
                'created_at': ANY,
            }]
        )

    def test_add_participant_type(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            '/api/activities/{}/'.format(self.activity.id), {'participant_types': [{
                'role': 'driver',
            }]},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.activity.refresh_from_db()
        self.assertEqual(
            list(self.activity.participant_types.order_by('role').values_list('role', flat=True)),
            ['approved', 'driver', 'member'],
        )

    def test_modify_participant_type_description(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            '/api/activities/{}/'.format(self.activity.id), {
                'participant_types': [{
                    'id': self.activity.participant_types.get(role='approved').id,
                    'description': 'yay it changed',
                }]
            },
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.activity.participant_types.get(role='approved').description, 'yay it changed')

    def test_can_modify_participant_type_role(self):
        pt = self.activity.participant_types.get(role=APPROVED)
        self.activity.add_participant(self.approved_member, participant_type=pt)
        self.assertEqual(self.activity.participants.count(), 1)
        self.client.force_login(user=self.member)
        response = self.client.patch(
            '/api/activities/{}/'.format(self.activity.id), {'participant_types': [{
                'id': pt.id,
                'role': 'cook',
            }]},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.activity.participants.count(), 0)

    def test_remove_participant_type(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            '/api/activities/{}/'.format(self.activity.id), {
                'participant_types': [{
                    'id': self.activity.participant_types.get(role='approved').id,
                    '_removed': True,
                }]
            },
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.activity.refresh_from_db()
        self.assertEqual(
            list(self.activity.participant_types.order_by('role').values_list('role', flat=True)),
            ['member'],
        )


class TestActivitiesListAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/activities/'

        # activity for group with one member and one place
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.activity_type = ActivityTypeFactory(group=self.group)
        self.active_place = PlaceFactory(group=self.group, status='active')
        self.inactive_place = PlaceFactory(group=self.group, status='created')

        participant_types = [
            {
                'role': 'member',
                'max_participants': 5,
            },
            {
                'role': 'member',
                'max_participants': 5,
            },
        ]

        ActivityFactory(
            activity_type=self.activity_type,
            place=self.active_place,
            participant_types=participant_types,
        )
        ActivityFactory(
            activity_type=self.activity_type,
            place=self.inactive_place,
            participant_types=participant_types,
        )

    def test_list_activities_for_active_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.active_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_activities_for_inactive_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.inactive_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_get_activity_for_inactive_place(self):
        self.client.force_login(user=self.member)
        activity = self.inactive_place.activities.first()
        response = self.client.get(f'/api/activities/{activity.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_activities_with_free_slots(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.active_place.id, 'slots': 'free'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
