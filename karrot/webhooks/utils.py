import logging
import requests
from django.conf import settings
from talon import quotations

from raven.contrib.django.raven_compat.models import client as sentry_client

logger = logging.getLogger(__name__)


def trim_with_talon(text):
    trimmed = quotations.extract_from_plain(text)

    return trimmed, len(trimmed.splitlines())


def trim_html_with_talon(html):
    return quotations.extract_from_html(html)


def trim_with_discourse(text):
    if settings.EMAIL_REPLY_TRIMMER_URL is None:
        logger.info('EMAIL_REPLY_TRIMMER_URL not set, skipping.')
        return text, len(text.splitlines())

    try:
        response = requests.post(
            settings.EMAIL_REPLY_TRIMMER_URL,
            json={
                'text': text
            },
            timeout=2,
        ).json()
    except requests.exceptions.ConnectionError:
        logger.warning('EMAIL_REPLY_TRIMMER_URL not accessible at ' + settings.EMAIL_REPLY_TRIMMER_URL + ', skipping.')
        sentry_client.captureException()
        trimmed = text
    else:
        trimmed = response['trimmed']

    return trimmed, len(trimmed.splitlines())
