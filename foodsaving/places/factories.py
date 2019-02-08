from factory import DjangoModelFactory, SubFactory, post_generation
from factory import LazyAttribute

from foodsaving.groups.factories import GroupFactory
from foodsaving.places.models import Place as PlaceModel
from foodsaving.utils.tests.fake import faker


class PlaceFactory(DjangoModelFactory):
    class Meta:
        model = PlaceModel

    @post_generation
    def subscribers(self, created, extracted, **kwargs):
        if created and extracted:
            for subscriber in extracted:
                self.storesubscription_set.create(user=subscriber)

    group = SubFactory(GroupFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = 'active'
