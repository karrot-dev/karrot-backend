from factory import DjangoModelFactory, LazyAttribute

from foodsaving.applications.models import GroupApplication
from foodsaving.utils.tests.fake import faker


class GroupApplicationFactory(DjangoModelFactory):
    class Meta:
        model = GroupApplication

    questions = LazyAttribute(lambda application: application.group.application_questions)
    answers = LazyAttribute(lambda x: faker.text())
