from factory import DjangoModelFactory, CREATE_STRATEGY, SubFactory, LazyAttribute

from foodsaving.cases.models import Case
from foodsaving.groups.factories import GroupFactory
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class CaseFactory(DjangoModelFactory):
    class Meta:
        model = Case
        strategy = CREATE_STRATEGY

    group = SubFactory(GroupFactory)
    created_by = SubFactory(UserFactory)
    topic = LazyAttribute(lambda x: faker.sentence(nb_words=4))
