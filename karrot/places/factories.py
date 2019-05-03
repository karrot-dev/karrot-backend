from factory import DjangoModelFactory, SubFactory, post_generation
from factory import LazyAttribute

from karrot.groups.factories import GroupFactory
from karrot.places.models import Place as PlaceModel
from karrot.utils.tests.fake import faker


class PlaceFactory(DjangoModelFactory):
    class Meta:
        model = PlaceModel

    group = SubFactory(GroupFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = 'active'

    @post_generation
    def subscribers(self, created, extracted, **kwargs):
        if created and extracted:
            for user in extracted:
                self.placesubscription_set.create(user=user)
