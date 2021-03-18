from factory import LazyAttribute, SubFactory, post_generation, SelfAttribute, Sequence
from factory.django import DjangoModelFactory

from karrot.groups.factories import GroupFactory
from karrot.places.models import Place as PlaceModel, PlaceType, PlaceStatus
from karrot.utils.tests.fake import faker


class PlaceTypeFactory(DjangoModelFactory):
    class Meta:
        model = PlaceType

    name = Sequence(lambda n: ' '.join(['PlaceType', str(n), faker.first_name()]))


class PlaceStatusFactory(DjangoModelFactory):
    class Meta:
        model = PlaceStatus

    name = Sequence(lambda n: ' '.join(['PlaceStatus', str(n), faker.first_name()]))


class PlaceFactory(DjangoModelFactory):
    class Meta:
        model = PlaceModel

    group = SubFactory(GroupFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = SubFactory(PlaceStatusFactory, group=SelfAttribute('..group'))
    place_type = SubFactory(PlaceTypeFactory, group=SelfAttribute('..group'))

    @post_generation
    def subscribers(self, created, extracted, **kwargs):
        if created and extracted:
            for user in extracted:
                self.placesubscription_set.create(user=user)
