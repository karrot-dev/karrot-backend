from factory import LazyAttribute, SubFactory
from factory.django import DjangoModelFactory

from karrot.subscriptions.models import WebPushSubscription
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class WebPushSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = WebPushSubscription

    user = SubFactory(UserFactory)
    endpoint = LazyAttribute(lambda x: faker.url())
    keys = LazyAttribute(lambda x: {'auth': faker.uuid4(), 'p256dh': faker.uuid4()})

    mobile = False
    browser = "firefox"
    version = "1.0"
    os = "linux"
