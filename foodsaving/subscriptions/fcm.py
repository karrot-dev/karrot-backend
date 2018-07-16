import logging

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
    tokens = [item.token for item in subscriptions]
    if len(tokens) < 1:
        return None

    response = _notify_multiple_devices(
        registration_ids=tokens,
        **fcm_options,
    )

    stats.pushed_via_subscription(subscriptions)
    return response


def _notify_multiple_devices(**kwargs):
    """
    Send a message to multiple devices.

    A simple wrapper of pyfcm's notify_multiple_devices.
    See https://github.com/olucurious/PyFCM/blob/master/pyfcm/fcm.py for more details on options, etc.
    """

    if fcm is None:
        return None

    response = fcm.notify_multiple_devices(**kwargs)
    tokens = kwargs.get('registration_ids', [])

    # check for invalid tokens and remove any corresponding push subscriptions
    for index, result in enumerate(response['results']):
        if 'error' in result and result['error'] == 'InvalidRegistration':
            PushSubscription.objects.filter(token=tokens[index]).delete()

    return response
