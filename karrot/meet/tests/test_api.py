from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.activities.factories import ActivityFactory
from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


def token_url(subject_type, *subject_ids):
    return f"/api/meet/{subject_type}:{','.join(str(val) for val in subject_ids)}/token/"


@override_settings(
    MEET_LIVEKIT_API_KEY="testapikey",
    MEET_LIVEKIT_API_SECRET="testapisecret",
)
class TestMeetAPI(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.nonmember_user = UserFactory()
        self.group = GroupFactory(members=[self.user])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place)

    def test_group_room_not_accessible_when_logged_out(self):
        response = self.client.get(token_url("group", self.group.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_group_room(self):
        self.client.force_login(user=self.user)
        response = self.client.get(token_url("group", self.group.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["room_id"], f"group:{self.group.id}")
        self.assertEqual(response.data["subject_type"], "group")
        self.assertEqual(response.data["subject_id"], self.group.id)
        self.assertIsNotNone(response.data["token"])

    def test_place_room(self):
        self.client.force_login(user=self.user)
        response = self.client.get(token_url("place", self.place.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_activity_room(self):
        self.client.force_login(user=self.user)
        response = self.client.get(token_url("activity", self.activity.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_group_room_unavailable_to_nonmembers(self):
        self.client.force_login(user=self.nonmember_user)
        response = self.client.get(token_url("group", self.group.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_place_room_unavailable_to_nonmembers(self):
        self.client.force_login(user=self.nonmember_user)
        response = self.client.get(token_url("place", self.place.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_random_room_not_available(self):
        self.client.force_login(user=self.user)
        response = self.client.get(token_url("somerandomgrouptype", 123))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(MEET_LIVEKIT_API_KEY=None)
    def test_404_if_api_key_not_set(self):
        self.client.force_login(user=self.user)
        response = self.client.get(f"/api/meet/group:{self.group.id}/token/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(MEET_LIVEKIT_API_SECRET=None)
    def test_404_if_api_secret_not_set(self):
        self.client.force_login(user=self.user)
        response = self.client.get(token_url("group", self.group.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
