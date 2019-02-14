from collections import namedtuple
from django.test import TestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.places.factories import PlaceFactory
from foodsaving.places.serializers import PlaceSerializer
from foodsaving.users.factories import UserFactory


class TestPlaceSerializer(TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.place = PlaceFactory()

    def test_place_instantiation(self):
        MockRequest = namedtuple('Request', ['user'])
        serializer = PlaceSerializer(self.place, context={'request': MockRequest(user=UserFactory())})
        self.assertEqual(serializer.data['name'], self.place.name)
