import logging
import requests
from django.conf import settings
from talon import quotations

logger = logging.getLogger(__name__)


def trim_with_talon(text):
    trimmed = quotations.extract_from_plain(text)

    return trimmed, len(trimmed.splitlines())


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
        logger.warning('email_reply_trimmer not accessible at ' + settings.EMAIL_REPLY_TRIMMER_URL + ', skipping.')
        trimmed = text
    else:
        trimmed = response['trimmed']

    return trimmed, len(trimmed.splitlines())
