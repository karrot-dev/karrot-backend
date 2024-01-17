from collections import defaultdict
from contextlib import contextmanager

from django.contrib.auth.hashers import make_password
from django.db.models.signals import (
    post_delete,
    post_init,
    post_migrate,
    post_save,
    pre_delete,
    pre_init,
    pre_migrate,
    pre_save,
)
from django.utils import timezone

from karrot.users.models import User


@contextmanager
def disabled_signals():
    receivers = defaultdict(list)
    signals = [
        pre_init,
        post_init,
        pre_save,
        post_save,
        pre_delete,
        post_delete,
        pre_migrate,
        post_migrate,
    ]
    try:
        for signal in signals:
            receivers[signal] = signal.receivers
            signal.receivers = []
        yield
    finally:
        for signal in signals:
            if signal in receivers:
                signal.receivers = receivers.get(signal, [])
                del receivers[signal]


def create_anonymous_user():
    """Create anon deleted user that we can use for missing user foreign key

    It might be there are import records that refers to users that are not imported
    ... and for cases where that field is required, we can use this to set it to
    an anonymous user.
    """
    return User.objects.create(
        description="",
        email=None,
        is_active=False,
        is_staff=False,
        mail_verified=False,
        unverified_email=None,
        username=make_password(None),
        display_name="",
        address=None,
        latitude=None,
        longitude=None,
        mobile_number="",
        deleted_at=timezone.now(),
        deleted=True,
    )
