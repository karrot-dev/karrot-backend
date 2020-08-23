from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from karrot.utils.tests.fake import faker


class InvitationFactory(DjangoModelFactory):
    class Meta:
        model = 'invitations.Invitation'

    email = Sequence(lambda n: str(n) + faker.email())
    invited_by = SubFactory('karrot.users.factories.UserFactory')
    group = SubFactory('karrot.groups.factories.GroupFactory')
