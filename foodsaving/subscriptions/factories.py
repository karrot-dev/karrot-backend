from random import random

from factory import DjangoModelFactory, SubFactory
from factory import LazyAttribute

from foodsaving.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class PushSubscriptionFactory(DjangoModelFactory):

    class Meta:
        model = PushSubscription

    user = SubFactory(UserFactory)
    token = LazyAttribute(lambda x: faker.uuid4())
    platform = LazyAttribute(lambda x: random.choice(list(PushSubscriptionPlatform)))
