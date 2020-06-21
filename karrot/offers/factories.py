import os

from django.core.files.uploadedfile import SimpleUploadedFile
from factory import DjangoModelFactory, SubFactory, LazyAttribute, post_generation

from karrot.groups.factories import GroupFactory
from karrot.offers.models import Offer
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class OfferFactory(DjangoModelFactory):
    class Meta:
        model = Offer

    group = SubFactory(GroupFactory)
    user = SubFactory(UserFactory)
    name = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    description = LazyAttribute(lambda x: faker.name())
    status = "active"

    @post_generation
    def images(self, created, extracted, **kwargs):
        if created and extracted:
            for index, image_path in enumerate(extracted):
                with open(image_path, "rb") as file:
                    upload = SimpleUploadedFile(
                        name=os.path.basename(image_path),
                        content=file.read(),
                        content_type="image/jpeg",
                    )
                    self.images.create(image=upload, position=index)
