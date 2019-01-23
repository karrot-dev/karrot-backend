from factory import DjangoModelFactory, LazyAttribute

from foodsaving.applications.models import Application
from foodsaving.utils.tests.fake import faker


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = Application

    questions = LazyAttribute(lambda application: application.group.application_questions)
    answers = LazyAttribute(lambda x: faker.text())
