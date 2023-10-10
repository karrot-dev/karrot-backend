import base64
import os

from factory import LazyAttribute, SubFactory
from factory.django import DjangoModelFactory

from karrot.subscriptions.models import WebPushSubscription
from karrot.users.factories import UserFactory
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from karrot.utils.tests.fake import faker

TEST_VAPID_PRIVATE_KEY = (
    "MHcCAQEEIPeN1iAipHbt8+/KZ2NIF8NeN24jqAmnMLFZEMocY8RboAoGCCqGSM49"
    "AwEHoUQDQgAEEJwJZq/GN8jJbo1GGpyU70hmP2hbWAUpQFKDByKB81yldJ9GTklB"
    "M5xqEwuPM7VuQcyiLDhvovthPIXx+gsQRQ=="
)


# Adapted from https://github.com/web-push-libs/pywebpush/blob/992efed89454629e741f8540f690bef681b17f2d/pywebpush/tests/test_webpush.py#L27
def _gen_subscription_info(self, recv_key=None, endpoint="https://example.com/"):
    if not recv_key:
        recv_key = ec.generate_private_key(ec.SECP256R1, default_backend())
    return {
        "endpoint": endpoint,
        "keys": {
            'auth': base64.urlsafe_b64encode(os.urandom(16)).strip(b'='),
            'p256dh': self._get_pubkey_str(recv_key),
        }
    }


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
