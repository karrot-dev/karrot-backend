from factory import LazyAttribute, SelfAttribute, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory

from karrot.groups.factories import GroupFactory
from karrot.places.models import Place as PlaceModel
from karrot.places.models import PlaceStatus, PlaceType
from karrot.utils.tests.fake import faker


class PlaceTypeFactory(DjangoModelFactory):
    class Meta:
        model = PlaceType

    name = Sequence(lambda n: " ".join(["PlaceType", str(n), faker.first_name()]))
    icon = "not-a-real-icon"


class PlaceStatusFactory(DjangoModelFactory):
    class Meta:
        model = PlaceStatus

    name = Sequence(lambda n: " ".join(["PlaceStatus", str(n), faker.first_name()]))
    colour = "000000"
    order = "a0"


class PlaceFactory(DjangoModelFactory):
    class Meta:
        model = PlaceModel

    group = SubFactory(GroupFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = SubFactory(PlaceStatusFactory, group=SelfAttribute("..group"))
    place_type = SubFactory(PlaceTypeFactory, group=SelfAttribute("..group"))

    @post_generation
    def subscribers(self, created, extracted, **kwargs):
        if created and extracted:
            for user in extracted:
                self.placesubscription_set.create(user=user)
