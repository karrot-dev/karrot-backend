import logging
from raven.contrib.django.raven_compat.models import client as sentry_client

from django.conf import settings
from pyfcm import FCMNotification

from foodsaving.subscriptions import stats
from foodsaving.subscriptions.models import PushSubscription

logger = logging.getLogger(__name__)

fcm = None

if hasattr(settings, 'FCM_SERVER_KEY'):
    fcm = FCMNotification(api_key=settings.FCM_SERVER_KEY)
else:
    logger.warning('Please configure FCM_SERVER_KEY in your settings to use push messaging')


def notify_subscribers(subscriptions, fcm_options):
    if len(subscriptions) < 1:
        return
    tokens = [item.token for item in subscriptions]

    success_indices, failure_indices = _notify_multiple_devices(
        registration_ids=tokens,
        **fcm_options,
    )

    success_subscriptions = [subscriptions[i] for i in success_indices]
    failure_subscriptions = [subscriptions[i] for i in failure_indices]

    stats.pushed_via_subscription(success_subscriptions, failure_subscriptions)


def _notify_multiple_devices(**kwargs):
    """
    Send a message to multiple devices.

    A simple wrapper of pyfcm's notify_multiple_devices.
    See https://github.com/olucurious/PyFCM/blob/master/pyfcm/fcm.py for more details on options, etc.
    """

    if fcm is None:
        return 0, 0

    response = fcm.notify_multiple_devices(**kwargs)
    sentry_client.extra_context(response)
    tokens = kwargs.get('registration_ids', [])

    # check for invalid tokens and remove any corresponding push subscriptions
    indexed_results = list(enumerate(response['results']))
    cleanup_tokens = [
        tokens[i] for (i, result) in indexed_results if result.get('error') in
        ('InvalidRegistration', 'NotRegistered', 'MismatchSenderId', 'InvalidApnsCredential')
    ]

    if len(cleanup_tokens) > 0:
        PushSubscription.objects.filter(token__in=cleanup_tokens).delete()

    success_indices = [i for (i, result) in indexed_results if 'error' not in result]
    failure_indices = [i for (i, result) in indexed_results if 'error' in result]

    # tell Sentry if there were errors
    if len(failure_indices) > 0:
        sentry_client.captureMessage('FCM error while sending', extra=response)
        logger.warning(
            'FCM error while sending: {} tokens successful, {} failed, {} removed from database'.format(
                len(success_indices), len(failure_indices), len(cleanup_tokens)
            )
        )

    return success_indices, failure_indices
