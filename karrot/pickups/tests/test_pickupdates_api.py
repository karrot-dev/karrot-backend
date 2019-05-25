from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.base.base_models import CustomDateTimeTZRange
from karrot.conversations.models import ConversationNotificationStatus
from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership, GroupStatus
from karrot.pickups.factories import PickupDateFactory
from karrot.pickups.models import to_range
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory


class TestPickupDatesAPI(APITestCase, ExtractPaginationMixin):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/api/pickup-dates/'

        # pickup date for group with one member and one place
        cls.member = UserFactory()
        cls.second_member = UserFactory()
        cls.group = GroupFactory(members=[cls.member, cls.second_member])
        cls.place = PlaceFactory(group=cls.group)
        cls.pickup = PickupDateFactory(place=cls.place)
        cls.pickup_url = cls.url + str(cls.pickup.id) + '/'
        cls.join_url = cls.pickup_url + 'add/'
        cls.leave_url = cls.pickup_url + 'remove/'
        cls.conversation_url = cls.pickup_url + 'conversation/'

        # not a member of the group
        cls.user = UserFactory()

        # another pickup date for above place
        cls.pickup_data = {
            'date': to_range(timezone.now() + relativedelta(days=2)).as_list(),
            'max_collectors': 5,
            'place': cls.place.id
        }

        # past pickup date
        cls.past_pickup_data = {
            'date': to_range(timezone.now() - relativedelta(days=1)).as_list(),
            'max_collectors': 5,
            'place': cls.place.id
        }
        cls.past_pickup = PickupDateFactory(place=cls.place, date=to_range(timezone.now() - relativedelta(days=1)))
        cls.past_pickup_url = cls.url + str(cls.past_pickup.id) + '/'
        cls.past_join_url = cls.past_pickup_url + 'add/'
        cls.past_leave_url = cls.past_pickup_url + 'remove/'

    def setUp(self):
        self.group.refresh_from_db()

    def test_create_pickup(self):
        response = self.client.post(self.url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_pickup_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_pickup_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_pickup_as_group_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.url, self.pickup_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_create_past_pickup_date_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.url, self.past_pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_create_pickup_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_pickups(self):
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_pickups_as_user(self):
        self.client.force_login(user=self.user)
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_list_pickups_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_pickups(self):
        response = self.client.get(self.pickup_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_retrieve_pickups_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.pickup_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_retrieve_pickups_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.get(self.pickup_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_patch_pickup(self):
        response = self.client.patch(self.pickup_url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_pickup_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.patch(self.pickup_url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_patch_pickup_as_group_member(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.pickup_url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_patch_pickup_as_group_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.patch(self.pickup_url, self.pickup_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_patch_max_collectors_to_negative_value_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.pickup_url, {'max_collectors': -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_past_pickup_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(self.past_pickup_url, self.pickup_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.pickup_url, {'max_collectors': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_join_pickup(self):
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_join_pickup_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_join_pickup_as_member(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # should have access to chat
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_pickup_order_by_sign_up(self):
        self.client.force_login(user=self.second_member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_login(user=self.member)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        collector_order = [self.second_member.id, self.member.id]
        response = self.client.get(self.pickup_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['collectors'], collector_order)

        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pickup = next(p for p in response.data if p['id'] == self.pickup.id)
        self.assertEqual(pickup['collectors'], collector_order)

        # reverse order
        collector = self.pickup.pickupdatecollector_set.earliest('created_at')
        collector.created_at = timezone.now()
        collector.save()
        collector_order = [self.member.id, self.second_member.id]

        response = self.client.get(self.pickup_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['collectors'], collector_order)

        response = self.get_results(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pickup = next(p for p in response.data if p['id'] == self.pickup.id)
        self.assertEqual(pickup['collectors'], collector_order)

    def test_join_pickup_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_join_pickup_as_member_activates_group(self):
        self.client.force_login(user=self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.join_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_join_pickup_without_max_collectors_as_member(self):
        self.client.force_login(user=self.member)
        p = PickupDateFactory(max_collectors=None, place=self.place)
        response = self.client.post('/api/pickup-dates/{}/add/'.format(p.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_join_full_pickup_fails(self):
        self.client.force_login(user=self.member)
        self.pickup.max_collectors = 1
        self.pickup.save()
        u2 = UserFactory()
        GroupMembership.objects.create(group=self.group, user=u2)
        self.pickup.add_collector(u2)
        response = self.client.post(self.join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['detail'], 'Pickup date is already full.')

    def test_join_past_pickup_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.post(self.past_join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_leave_pickup(self):
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_leave_pickup_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_leave_pickup_as_member(self):
        self.client.force_login(user=self.member)
        self.pickup.add_collector(self.member)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # should be removed from chat
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['notifications'], ConversationNotificationStatus.NONE.value)

    def test_leave_pickup_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.pickup.add_collector(newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.leave_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_leave_pickup_activates_group(self):
        self.client.force_login(user=self.member)
        self.pickup.add_collector(self.member)
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.post(self.leave_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_leave_past_pickup_fails(self):
        self.client.force_login(user=self.member)
        self.past_pickup.add_collector(self.member)
        response = self.client.post(self.past_leave_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_get_conversation_as_collector(self):
        self.client.force_login(user=self.member)
        self.pickup.add_collector(self.member)

        # can get via pickup
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.member.id, response.data['participants'])
        self.assertEqual(response.data['type'], 'pickup')

        # can get via conversations
        conversation_id = self.pickup.conversation.id
        response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # can write a message
        response = self.client.post('/api/messages/', {
            'conversation': response.data['id'],
            'content': 'hey',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_can_participate_in_conversation_as_noncollector(self):
        self.client.force_login(user=self.member)

        # can get via pickup
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # can get via conversation
        conversation_id = self.pickup.conversation.id
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

        # cannot get via pickup
        response = self.client.get(self.conversation_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # cannot get via conversation info
        conversation_id = self.pickup.conversation.id
        response = self.client.get('/api/conversations/{}/'.format(conversation_id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # cannot write a message
        conversation_id = self.pickup.conversation.id
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
            self.pickup_url, {
                'date': [start, end],
                'has_duration': True,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.date, CustomDateTimeTZRange(start, end))

    def test_remove_duration_resets_end_date(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        end = timezone.now() + timedelta(hours=2)
        response = self.client.patch(self.pickup_url, {'date': [start, end], 'has_duration': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = self.client.patch(self.pickup_url, {'has_duration': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.date, CustomDateTimeTZRange(start, start + timedelta(minutes=30)))

    def test_patch_start_date_only_uses_default_duration(self):
        self.client.force_login(user=self.member)
        start = timezone.now() + timedelta(hours=1)
        response = self.client.patch(
            self.pickup_url, {
                'date': [start],
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.date.end, start + timedelta(minutes=30))

    def test_patch_date_with_single_date_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.pickup_url, {
                'date': timezone.now(),
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_patch_end_date_only_fails(self):
        self.client.force_login(user=self.member)
        response = self.client.patch(
            self.pickup_url, {
                'date': [None, timezone.now()],
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_cannot_mark_as_done(self):
        # This is just temporarily - if we need this feature at some point, we should enable it
        # Make sure to create history entries!
        self.client.force_login(user=self.member)
        self.assertEqual(self.pickup.is_done, False)
        response = self.client.patch(self.pickup_url, {'is_done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.pickup.refresh_from_db()
        self.assertFalse(self.pickup.is_done, False)


class TestPickupDatesListAPI(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.url = '/api/pickup-dates/'

        # pickup date for group with one member and one place
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.active_place = PlaceFactory(group=self.group, status='active')
        self.inactive_place = PlaceFactory(group=self.group, status='created')

        PickupDateFactory(place=self.active_place)
        PickupDateFactory(place=self.inactive_place)

    def test_list_pickups_for_active_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.active_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_pickups_for_inactive_place(self):
        self.client.force_login(user=self.member)
        response = self.get_results(self.url, {'place': self.inactive_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
