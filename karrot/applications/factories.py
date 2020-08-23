from factory import LazyAttribute
from factory.django import DjangoModelFactory

from karrot.applications.models import Application
from karrot.utils.tests.fake import faker


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = Application

    questions = LazyAttribute(lambda application: application.group.application_questions)
    answers = LazyAttribute(lambda x: faker.text())
