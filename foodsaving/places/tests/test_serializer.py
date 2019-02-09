from django.test import TestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.places.factories import PlaceFactory
from foodsaving.places.serializers import PlaceSerializer


class TestPlaceSerializer(TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.place = PlaceFactory()

    def test_place_instantiation(self):
        serializer = PlaceSerializer(self.place)
        self.assertEqual(serializer.data['name'], self.place.name)
