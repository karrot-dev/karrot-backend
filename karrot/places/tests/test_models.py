from django.db import DataError, IntegrityError
from django.test import TestCase
from django.utils import timezone

from karrot.groups.factories import GroupFactory
from karrot.places.models import Place
from karrot.users.factories import UserFactory


class TestPlaceModel(TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.defaults = {
            "group": self.group,
            "place_type": self.group.place_types.first(),
            "status": self.group.place_statuses.first(),
        }

    def test_create_fails_if_name_too_long(self):
        with self.assertRaises(DataError):
            Place.objects.create(name="a" * 81, **self.defaults)

    def test_create_place_with_same_name_fails(self):
        Place.objects.create(name="abcdef", **self.defaults)
        with self.assertRaises(IntegrityError):
            Place.objects.create(name="abcdef", **self.defaults)

    def test_create_place_with_same_name_in_different_groups_works(self):
        Place.objects.create(name="abcdef", **self.defaults)
        Place.objects.create(name="abcdef", **{**self.defaults, "group": GroupFactory()})

    def test_get_archived_status(self):
        s = Place.objects.create(name="my place", **self.defaults)
        self.assertFalse(s.is_archived)

        s.archived_at = timezone.now()
        s.save()
        self.assertTrue(s.is_archived)

    def test_removes_subscription_when_leaving_group(self):
        place = Place.objects.create(name="abcdef", **self.defaults)
        user = UserFactory()
        self.group.add_member(user)
        place.placesubscription_set.create(user=user)

        self.group.remove_member(user)

        self.assertFalse(place.placesubscription_set.filter(user=user).exists())
        conversation = place.conversation
        self.assertFalse(conversation.conversationparticipant_set.filter(user=user).exists())
