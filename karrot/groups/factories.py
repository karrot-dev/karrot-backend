import os

from django.core.files.uploadedfile import SimpleUploadedFile
from factory import post_generation, LazyAttribute, Sequence
from factory.django import DjangoModelFactory

from karrot.groups import roles
from karrot.groups.models import Group as GroupModel, GroupStatus, GroupNotificationType
from karrot.utils.tests.fake import faker


class GroupFactory(DjangoModelFactory):
    class Meta:
        model = GroupModel

    @post_generation
    def members(self, created, extracted, **kwargs):
        if created and extracted:
            for member in extracted:
                membership = self.groupmembership_set.create(user=member, roles=[roles.GROUP_EDITOR])
                membership.add_notification_types([
                    GroupNotificationType.NEW_APPLICATION,
                    GroupNotificationType.NEW_OFFER,
                ])
                membership.save()

    @post_generation
    def newcomers(self, created, extracted, **kwargs):
        if created and extracted:
            for member in extracted:
                self.groupmembership_set.create(user=member)

    @post_generation
    def photo(self, created, extracted, **kwargs):
        if created and extracted:
            image_path = extracted
            with open(image_path, 'rb') as file:
                upload = SimpleUploadedFile(
                    name=os.path.basename(image_path),
                    content=file.read(),
                    content_type='image/jpeg',
                )
                self.photo = upload
                self.save()

    @post_generation
    def add_default_types(self, created, extracted, **kwargs):
        # this feels like abusing the factory system as this is not actually a field, but hey ho!
        self.create_default_types()

    name = Sequence(lambda n: ' '.join(['Group', str(n), faker.name()]))
    description = LazyAttribute(lambda x: faker.sentence(nb_words=40))
    public_description = LazyAttribute(lambda x: faker.sentence(nb_words=20))
    application_questions = LazyAttribute(lambda x: faker.sentence(nb_words=20))
    welcome_message = LazyAttribute(lambda x: faker.sentence(nb_words=30))


class PlaygroundGroupFactory(GroupFactory):
    status = GroupStatus.PLAYGROUND.value


class InactiveGroupFactory(GroupFactory):
    status = GroupStatus.INACTIVE.value
