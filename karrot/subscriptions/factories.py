import random

from factory import LazyAttribute, SubFactory
from factory.django import DjangoModelFactory

from karrot.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class PushSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = PushSubscription

    user = SubFactory(UserFactory)
    token = LazyAttribute(lambda x: faker.uuid4())
    platform = LazyAttribute(lambda x: random.choice(list(PushSubscriptionPlatform)).value)
