from django.db import DataError
from django.db import IntegrityError
from django.test import TestCase

from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import Group, GroupMembership
from foodsaving.users.factories import UserFactory


class TestGroupModel(TestCase):
    def test_create_fails_if_name_too_long(self):
        with self.assertRaises(DataError):
            Group.objects.create(name='a' * 81)

    def test_create_group_with_same_name_fails(self):
        Group.objects.create(name='abcdef')
        with self.assertRaises(IntegrityError):
            Group.objects.create(name='abcdef')

    def test_roles_initialized(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        membership = GroupMembership.objects.filter(user=user, group=group).first()
        self.assertIn(roles.GROUP_MEMBERSHIP_MANAGER, membership.roles)

    def test_approved_member_count(self):
        user = [UserFactory() for _ in range(2)]
        group = GroupFactory(members=user)
        self.assertEquals(group.approved_member_count(), 2)
        # Adding a non-approved user should not increment active count
        group.add_member(UserFactory(), roles=[])
        self.assertEquals(group.approved_member_count(), 2)
        # Adding an approved user should not increment active count
        group.add_member(UserFactory())
        self.assertEquals(group.approved_member_count(), 3)


