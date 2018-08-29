from factory import DjangoModelFactory, post_generation, LazyAttribute, Sequence

from foodsaving.groups import roles
from foodsaving.groups.models import Group as GroupModel, GroupMembership, GroupStatus
from foodsaving.utils.tests.fake import faker


class GroupFactory(DjangoModelFactory):
    class Meta:
        model = GroupModel

    @post_generation
    def editors(self, created, extracted, **kwargs):
        if created and extracted:
            for member in extracted:
                GroupMembership.objects.create(group=self, user=member, roles=[roles.GROUP_EDITOR])

    @post_generation
    def newcomers(self, created, extracted, **kwargs):
        if created and extracted:
            for member in extracted:
                GroupMembership.objects.create(group=self, user=member)

    name = Sequence(lambda n: ' '.join(['Group', str(n), faker.name()]))
    description = LazyAttribute(lambda x: faker.sentence(nb_words=40))
    public_description = LazyAttribute(lambda x: faker.sentence(nb_words=20))
    application_questions = LazyAttribute(lambda x: faker.sentence(nb_words=20))


class PlaygroundGroupFactory(GroupFactory):
    status = GroupStatus.PLAYGROUND.value


class InactiveGroupFactory(GroupFactory):
    status = GroupStatus.INACTIVE.value
