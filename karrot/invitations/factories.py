import factory

from karrot.utils.tests.fake import faker


class InvitationFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'invitations.Invitation'

    email = factory.Sequence(lambda n: str(n) + faker.email())
    invited_by = factory.SubFactory('karrot.users.factories.UserFactory')
    group = factory.SubFactory('karrot.groups.factories.GroupFactory')
