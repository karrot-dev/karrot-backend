from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.conversations.factories import ConversationFactory
from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupMembership
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.trust.models import Trust
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class TestUsersAPI(APITestCase):
    def test_user_becomes_editor_with_enough_trust(self):
        editors = [UserFactory() for _ in range(3)]
        group = GroupFactory(members=editors)

        newcomer = UserFactory()
        group.add_member(newcomer)

        [Trust.objects.create(user=newcomer, group=group, given_by=editor) for editor in editors[:2]]
        membership = GroupMembership.objects.get(user=newcomer, group=group)
        self.assertNotIn(roles.GROUP_EDITOR, membership.roles)

        self.client.force_login(user=editors[2])
        response = self.client.post('/api/trust/', {
            'group': group.id,
            'user': newcomer.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        membership.refresh_from_db()
        self.assertIn(roles.GROUP_EDITOR, membership.roles)



