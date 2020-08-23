from factory import SubFactory, LazyAttribute, post_generation
from factory.django import DjangoModelFactory

from karrot.groups.factories import GroupFactory
from karrot.offers.models import Offer
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker
from karrot.utils.tests.images import image_upload_for


class OfferFactory(DjangoModelFactory):
    class Meta:
        model = Offer

    group = SubFactory(GroupFactory)
    user = SubFactory(UserFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = 'active'

    @post_generation
    def images(self, created, extracted, **kwargs):
        if created and extracted:
            for index, image_path in enumerate(extracted):
                self.images.create(image=image_upload_for(image_path), position=index)
