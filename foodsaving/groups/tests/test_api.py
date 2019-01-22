import json
import os

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from unittest.mock import patch, call

from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory, PlaygroundGroupFactory
from foodsaving.groups.models import Group as GroupModel, GroupMembership, Agreement, UserAgreement, \
    GroupNotificationType, get_default_notification_types, Group
from foodsaving.groups.stats import group_tags
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.pickups.models import to_range
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class TestGroupsInfoAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member], application_questions='')
        self.url = '/api/groups-info/'

    def test_list_groups_as_anon(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_groups_as_user(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_group_as_anon(self):
        url = self.url + str(self.group.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Hey there', response.data['application_questions'])

    def test_retrieve_group_as_user(self):
        self.client.force_login(user=self.user)
        url = self.url + str(self.group.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_group_as_member(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestGroupsAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member], is_open=True)
        self.group_with_password = GroupFactory(password='abc', is_open=True)
        self.join_password_url = '/api/groups/{}/join/'.format(self.group_with_password.id)
        self.url = '/api/groups/'
        self.group_data = {
            'name': faker.name(),
            'description': faker.text(),
            'address': faker.address(),
            'latitude': faker.latitude(),
            'longitude': faker.longitude(),
            'timezone': 'Europe/Berlin'
        }

    def test_create_group(self):
        self.client.force_login(user=self.user)
        data = {'name': 'random_name', 'description': 'still alive', 'timezone': 'Europe/Berlin'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['name'], data['name'])
        self.assertEqual(GroupModel.objects.get(name=data['name']).description, data['description'])

    def test_create_group_with_location(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.url, self.group_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], self.group_data['name'])
        self.assertEqual(
            GroupModel.objects.get(name=self.group_data['name']).description, self.group_data['description']
        )
        self.assertEqual(response.data['address'], self.group_data['address'])

    def test_create_group_fails_if_not_logged_in(self):
        data = {'name': 'random_name', 'description': 'still alive'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_groups(self):
        self.client.force_login(user=self.member)
        with self.assertNumQueries(5):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['id'], self.group.id)

    def test_retrieve_group_as_nonmember(self):
        self.client.force_login(user=self.user)
        url = self.url + str(self.group.id) + '/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_group_as_member(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        with self.assertNumQueries(5):
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('photo_urls', response.data)

    def test_patch_group(self):
        url = self.url + str(self.group.id) + '/'
        response = self.client.patch(url, self.group_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_group_as_user(self):
        self.client.force_login(user=self.user)
        url = self.url + str(self.group.id) + '/'
        response = self.client.patch(url, self.group_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_group_as_member(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        response = self.client.patch(url, self.group_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patch_group_as_newcomer(self):
        newcomer = UserFactory()
        self.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        url = self.url + str(self.group.id) + '/'
        response = self.client.patch(url, self.group_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_timezone_to_invalid_value_fails(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        response = self.client.patch(url, {'timezone': 'alksjdflkajw'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'timezone': ['Unknown timezone']})

    def test_change_is_open_fails(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        self.client.patch(url, {'is_open': False})
        self.assertTrue(Group.objects.get(id=self.group.id).is_open)

    def test_get_conversation(self):
        self.client.force_login(user=self.member)
        response = self.client.get('/api/groups/{}/conversation/'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(self.member.id, response.data['participants'])
        self.assertEqual(response.data['type'], 'group')

    def test_join_group(self):
        self.client.force_login(user=self.user)
        response = self.client.post('/api/groups/{}/join/'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_group_with_password(self):
        self.client.force_login(user=self.user)
        response = self.client.post(self.join_password_url, {"password": "abc"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_group_fails_if_not_logged_in(self):
        response = self.client.post('/api/groups/{}/join/'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_join_non_open_group(self):
        non_open_group = GroupFactory(is_open=False)
        self.client.force_login(user=self.user)
        response = self.client.post('/api/groups/{}/join/'.format(non_open_group.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_leave_group(self):
        store = StoreFactory(group=self.group)
        pickupdate = PickupDateFactory(
            store=store,
            collectors=[self.member, self.user],
            date=to_range(timezone.now() + relativedelta(weeks=1), minutes=30)
        )
        past_pickupdate = PickupDateFactory(
            store=store,
            collectors=[
                self.member,
            ],
            date=to_range(timezone.now() - relativedelta(weeks=1), minutes=30)
        )
        unrelated_pickupdate = PickupDateFactory(
            date=to_range(timezone.now() + relativedelta(weeks=1), minutes=30),
            collectors=[
                self.member,
            ],
        )
        GroupMembership.objects.create(group=unrelated_pickupdate.store.group, user=self.member)

        self.client.force_login(user=self.member)
        response = self.client.post('/api/groups/{}/leave/'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(pickupdate.collectors.get_queryset().filter(id=self.member.id).exists())
        self.assertTrue(past_pickupdate.collectors.get_queryset().filter(id=self.member.id).exists())
        self.assertTrue(unrelated_pickupdate.collectors.get_queryset().filter(id=self.member.id).exists())

    def test_leave_group_fails_if_not_logged_in(self):
        response = self.client.post('/api/groups/{}/leave/'.format(self.group.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_group_as_nonmember(self):
        self.client.force_login(user=self.user)
        url = self.url + str(self.group.id) + '/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_group_as_member(self):
        self.client.force_login(user=self.member)
        url = self.url + str(self.group.id) + '/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestUploadGroupPhoto(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.url = '/api/groups/' + str(self.group.id) + '/'
        self.photo_file = os.path.join(os.path.dirname(__file__), './photo.jpg')

    def test_upload_and_delete_photo(self):
        self.client.force_login(user=self.user)
        response = self.client.get(self.url)
        self.assertTrue('full_size' not in response.data['photo_urls'])

        History.objects.all().delete()

        with open(self.photo_file, 'rb') as photo:
            response = self.client.patch(self.url, {'photo': photo})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.get(self.url)
        self.assertTrue('full_size' in response.data['photo_urls'])
        self.assertTrue('thumbnail' in response.data['photo_urls'])
        self.assertTrue(response.data['photo_urls']['full_size'].startswith('http://testserver'))

        self.assertEqual(History.objects.count(), 1)
        self.assertEqual(History.objects.first().typus, HistoryTypus.GROUP_CHANGE_PHOTO)

        History.objects.all().delete()

        # delete photo
        response = self.client.patch(self.url, {'photo': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.get(self.url)
        self.assertTrue('full_size' not in response.data['photo_urls'])
        self.assertTrue('thumbnail' not in response.data['photo_urls'])

        self.assertEqual(History.objects.count(), 1)
        self.assertEqual(History.objects.first().typus, HistoryTypus.GROUP_DELETE_PHOTO)


class TestPlaygroundGroupAPI(APITestCase):
    def setUp(self):
        self.member = UserFactory()
        self.group = PlaygroundGroupFactory(members=[self.member], password='')

    def test_change_password_has_no_effect(self):
        self.client.force_login(user=self.member)
        url = reverse('group-detail', kwargs={'pk': self.group.id})
        response = self.client.patch(url, data={'public_description': 'buy our nice horse'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.group.refresh_from_db()
        self.assertEqual(self.group.password, '')


class TestGroupMembershipsAPI(APITestCase):
    def setUp(self):
        self.active_user = UserFactory()
        self.inactive_user = UserFactory()
        self.group = GroupFactory(members=[self.active_user, self.inactive_user])
        self.active_membership = self.group.groupmembership_set.get(user=self.active_user)
        self.inactive_membership = self.group.groupmembership_set.get(user=self.inactive_user)
        self.inactive_membership.inactive_at = timezone.now()
        self.inactive_membership.save()

    def test_shows_user_active(self):
        self.client.force_login(user=self.active_user)
        response = self.client.get('/api/groups/{}/'.format(self.group.id))
        self.assertEqual(response.data['memberships'][self.active_user.id]['active'], True)

    def test_shows_user_inactive(self):
        self.client.force_login(user=self.active_user)
        response = self.client.get('/api/groups/{}/'.format(self.group.id))
        self.assertEqual(response.data['memberships'][self.inactive_user.id]['active'], False)


class TestGroupMemberLastSeenAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.membership = self.group.groupmembership_set.get(user=self.user)
        self.membership.inactive_at = timezone.now() - relativedelta(months=7)
        self.membership.removal_notification_at = timezone.now() - relativedelta(hours=2)
        self.membership.save()

    @patch('foodsaving.groups.stats.write_points')
    def test_mark_user_as_seen_in_group(self, write_points):
        before = timezone.now()
        self.assertLess(self.membership.lastseen_at, before)

        self.client.force_login(user=self.user)
        response = self.client.post('/api/groups/{}/mark_user_active/'.format(self.group.id), format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.membership.refresh_from_db()
        self.assertGreater(self.membership.lastseen_at, before)
        self.assertEqual(self.membership.inactive_at, None)
        self.assertEqual(self.membership.removal_notification_at, None)

        expected_stats = [
            call([{
                'measurement': 'karrot.events',
                'tags': group_tags(self.group),
                'fields': {
                    'group_member_returned': 1,
                    'group_member_returned_seconds_since_marked_for_removal': 60 * 60 * 2,
                },
            }]),
            call([{
                'measurement': 'karrot.events',
                'tags': group_tags(self.group),
                'fields': {
                    'group_activity': 1,
                },
            }]),
        ]

        self.assertEqual(write_points.call_args_list, expected_stats)


class TestGroupNotificationTypes(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.membership = GroupMembership.objects.get(group=self.group, user=self.user)

    def test_add_notification_type(self):
        self.client.force_login(user=self.user)

        self.membership.notification_types = []
        self.membership.save()

        response = self.client.put(
            '/api/groups/{}/notification_types/{}/'.format(self.group.id, GroupNotificationType.WEEKLY_SUMMARY)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.notification_types, [GroupNotificationType.WEEKLY_SUMMARY])

    def test_remove_notification_type(self):
        self.client.force_login(user=self.user)
        self.membership.notification_types = [GroupNotificationType.WEEKLY_SUMMARY]
        self.membership.save()
        response = self.client.delete(
            '/api/groups/{}/notification_types/{}/'.format(self.group.id, GroupNotificationType.WEEKLY_SUMMARY)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.notification_types, [])

    def test_appears_in_group_detail(self):
        self.client.force_login(user=self.user)
        response = self.client.get('/api/groups/{}/'.format(self.group.id))
        self.assertEqual(response.data['notification_types'], get_default_notification_types())


class TestAgreementsAPI(APITestCase):
    def setUp(self):
        self.normal_member = UserFactory()
        self.agreement_manager = UserFactory()
        self.group = GroupFactory(members=[self.normal_member, self.agreement_manager])
        self.agreement = Agreement.objects.create(group=self.group, title=faker.text(), content=faker.text())
        membership = GroupMembership.objects.get(group=self.group, user=self.agreement_manager)
        membership.roles.append(roles.GROUP_AGREEMENT_MANAGER)
        membership.save()

        # other group/agreement that neither user is part of
        self.other_group = GroupFactory()
        self.other_agreement = Agreement.objects.create(
            group=self.other_group, title=faker.text(), content=faker.text()
        )

    def test_can_create_agreement(self):
        self.client.force_login(user=self.agreement_manager)
        response = self.client.post(
            '/api/agreements/',
            {
                'title': faker.text(),
                'content': faker.text(),
                'group': self.group.id
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_agreement_for_another_group(self):
        self.client.force_login(user=self.agreement_manager)
        response = self.client.post(
            '/api/agreements/',
            {
                'title': faker.text(),
                'content': faker.text(),
                'group': self.other_group.id
            }
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_update_agreement(self):
        self.client.force_login(user=self.agreement_manager)
        response = self.client.patch('/api/agreements/{}/'.format(self.agreement.id), {'title': faker.name()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_normal_member_cannot_create_agreement(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.post(
            '/api/agreements/',
            {
                'title': faker.name(),
                'content': faker.text(),
                'group': self.group.id
            }
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_agreements(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.get('/api/agreements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['agreed'], False)

    def test_view_agreement(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.get('/api/agreements/{}/'.format(self.agreement.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.agreement.title)
        self.assertEqual(response.data['content'], self.agreement.content)

    def test_can_agree(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.post('/api/agreements/{}/agree/'.format(self.agreement.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['agreed'], True)

    def test_can_agree_is_idempotent(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.post('/api/agreements/{}/agree/'.format(self.agreement.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post('/api/agreements/{}/agree/'.format(self.agreement.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(UserAgreement.objects.filter(user=self.normal_member, agreement=self.agreement).count(), 1)

    def test_cannot_view_agreements_for_other_groups(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.get('/api/agreements/{}/'.format(self.other_agreement.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_agree_agreements_for_other_groups(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.post('/api/agreements/{}/agree/'.format(self.other_agreement.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_set_group_agreement(self):
        self.client.force_login(user=self.agreement_manager)
        response = self.client.patch('/api/groups/{}/'.format(self.group.id), {'active_agreement': self.agreement.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_unset_group_agreement(self):
        self.client.force_login(user=self.agreement_manager)
        self.group.active_agreement = self.agreement
        self.group.save()
        # using json.dumps as otherwise it sends an empty string, but we want it to send json value "null"
        response = self.client.patch(
            '/api/groups/{}/'.format(self.group.id),
            json.dumps({
                'active_agreement': None
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['active_agreement'], None)

    def test_cannot_set_group_agreement_if_for_wrong_group(self):
        self.client.force_login(user=self.agreement_manager)
        response = self.client.patch(
            '/api/groups/{}/'.format(self.group.id),
            {'active_agreement': self.other_agreement.id}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_normal_user_cannot_group_agreement(self):
        self.client.force_login(user=self.normal_member)
        response = self.client.patch('/api/groups/{}/'.format(self.group.id), {'active_agreement': self.agreement.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
