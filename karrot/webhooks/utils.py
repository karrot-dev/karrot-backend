import logging
from base64 import b32decode, b32encode

import requests
import talon
from anymail.exceptions import AnymailAPIError
from django.conf import settings
from django.core import signing
from raven.contrib.django.raven_compat.models import client as sentry_client
from talon import quotations

from karrot.webhooks import stats
from karrot.webhooks.emails import prepare_incoming_email_rejected_email

logger = logging.getLogger(__name__)

# register talon xpath extensions, to avoid XPathEvalError
talon.init()


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
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logger.warning('EMAIL_REPLY_TRIMMER_URL not accessible at ' + settings.EMAIL_REPLY_TRIMMER_URL + ', skipping.')
        sentry_client.captureException()
        trimmed = text
    else:
        trimmed = response['trimmed']

    return trimmed, len(trimmed.splitlines())


def parse_local_part(part):
    # cut 'b32+' from beginning of local part
    signed_part = b32decode(part[4:], casefold=True)
    signed_part_decoded = signed_part.decode('utf8')
    parts = signing.loads(signed_part_decoded)
    if len(parts) == 2:
        parts.append(None)  # in place of thread id
    return parts


def make_local_part(conversation, user, thread=None):
    data = [conversation.id, user.id]
    if thread is not None:
        data.append(thread.id)
    signed_part = signing.dumps(data)
    signed_part = signed_part.encode('utf8')
    b32 = b32encode(signed_part)
    b32_string = 'b32+' + b32.decode('utf8')
    return b32_string


def notify_about_rejected_email(user, content):
    try:
        prepare_incoming_email_rejected_email(user, content).send()
    except AnymailAPIError:
        sentry_client.captureException()
    stats.incoming_email_rejected()
