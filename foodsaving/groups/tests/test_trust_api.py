from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership, Trust
from foodsaving.users.factories import UserFactory


class TestTrustThreshold(TestCase):
    def create_group_with_members(self, member_count):
        self.members = [UserFactory() for _ in range(member_count)]
        self.group = GroupFactory(editors=self.members)
        two_days_ago = timezone.now() - relativedelta(days=2)
        GroupMembership.objects.filter(group=self.group).update(created_at=two_days_ago)

    def test_min_threshold(self):
        self.create_group_with_members(1)
        self.assertEqual(
            self.group.get_trust_threshold_for_newcomer(),
            1,
        )

    def test_ramp_up_threshold(self):
        self.create_group_with_members(5)
        self.assertEqual(
            self.group.get_trust_threshold_for_newcomer(),
            2,
        )

    def test_max_threshold(self):
        self.create_group_with_members(6)
        self.assertEqual(
            self.group.get_trust_threshold_for_newcomer(),
            3,
        )

    def test_ignores_recently_joined_users(self):
        self.create_group_with_members(1)
        [self.group.add_member(UserFactory()) for _ in range(5)]
        self.assertEqual(
            self.group.get_trust_threshold_for_newcomer(),
            1,
        )


class TestTrustAPI(APITestCase):
    def setUp(self):
        self.member1 = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(editors=[self.member1, self.member2])

    def test_give_trust(self):
        self.client.force_login(user=self.member1)

        url = reverse('group-trust-user', args=(self.group.id, self.member2.id))
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Trust.objects.filter(
                membership__group=self.group,
                membership__user=self.member2,
                given_by=self.member1,
            ).exists()
        )

    def test_can_only_give_trust_once(self):
        membership = GroupMembership.objects.get(user=self.member2, group=self.group)
        Trust.objects.create(membership=membership, given_by=self.member1)
        self.client.force_login(user=self.member1)

        url = reverse('group-trust-user', args=(self.group.id, self.member2.id))
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_give_trust_to_self(self):
        self.client.force_login(user=self.member1)

        url = reverse('group-trust-user', args=(self.group.id, self.member1.id))
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Trust.objects.filter(
                membership__group=self.group,
                membership__user=self.member2,
                given_by=self.member1,
            ).exists()
        )


class TestTrustList(APITestCase):
    def setUp(self):
        self.member1 = UserFactory()
        self.member2 = UserFactory()
        self.group = GroupFactory(editors=[self.member1, self.member2])

        membership = GroupMembership.objects.get(user=self.member2, group=self.group)
        Trust.objects.create(membership=membership, given_by=self.member1)
        membership = GroupMembership.objects.get(user=self.member1, group=self.group)
        Trust.objects.create(membership=membership, given_by=self.member2)

    def test_list_trust_for_group(self):
        self.client.force_login(user=self.member1)
        response = self.client.get('/api/groups/{}/'.format(self.group.id))
        self.assertEqual(response.data['memberships'][self.member1.id]['trusted_by'], [self.member2.id])
        self.assertEqual(response.data['memberships'][self.member2.id]['trusted_by'], [self.member1.id])

    def test_list_trust_for_user(self):
        self.client.force_login(user=self.member1)
        response = self.client.get('/api/users/{}/profile/'.format(self.member2.id))
        self.assertEqual(response.data['memberships'][self.group.id]['trusted_by'], [self.member1.id])
