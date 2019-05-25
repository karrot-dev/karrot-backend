from factory import DjangoModelFactory, post_generation, LazyAttribute, Sequence

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
                membership.add_notification_types([GroupNotificationType.NEW_APPLICATION])
                membership.save()

    @post_generation
    def newcomers(self, created, extracted, **kwargs):
        if created and extracted:
            for member in extracted:
                self.groupmembership_set.create(user=member)

    name = Sequence(lambda n: ' '.join(['Group', str(n), faker.name()]))
    description = LazyAttribute(lambda x: faker.sentence(nb_words=40))
    public_description = LazyAttribute(lambda x: faker.sentence(nb_words=20))
    application_questions = LazyAttribute(lambda x: faker.sentence(nb_words=20))
    welcome_message = LazyAttribute(lambda x: faker.sentence(nb_words=30))


class PlaygroundGroupFactory(GroupFactory):
    status = GroupStatus.PLAYGROUND.value


class InactiveGroupFactory(GroupFactory):
    status = GroupStatus.INACTIVE.value
