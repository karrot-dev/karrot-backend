from email.utils import formataddr as real_formataddr

import html2text
from anymail.exceptions import AnymailAPIError
from anymail.message import AnymailMessage
from babel.dates import format_date, format_time, format_datetime
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string, get_template
from django.utils import translation, timezone
from django.utils.text import Truncator
from django.utils.timezone import get_current_timezone
from django.utils.translation import to_locale, get_language
from jinja2 import Environment

from config import settings
from karrot.utils import stats
from karrot.utils.frontend_urls import place_url, user_url, absolute_url, group_photo_or_karrot_logo_url, \
    group_wall_url


def date_filter(value):
    return format_date(
        value.astimezone(get_current_timezone()),
        format='full',
        locale=to_locale(get_language()),
    )


def time_filter(value):
    return format_time(
        value,
        format='short',
        locale=to_locale(get_language()),
        tzinfo=get_current_timezone(),
    )


def datetime_filter(value):
    return format_datetime(
        value,
        format='medium',
        locale=to_locale(get_language()),
        tzinfo=get_current_timezone(),
    )


def jinja2_environment(**options):
    env = Environment(**options)
    env.filters['date'] = date_filter
    env.filters['time'] = time_filter
    env.filters['datetime'] = datetime_filter
    env.globals['place_url'] = place_url
    env.globals['user_url'] = user_url
    env.globals['group_wall_url'] = group_wall_url
    env.globals['absolute_url'] = absolute_url
    return env


def generate_plaintext_from_html(html):
    # always create an instance as it keeps state inside it
    # and will create ever increment link references otherwise
    h = html2text.HTML2Text()
    h.ignore_tables = True
    h.inline_links = False
    h.ignore_images = True
    h.wrap_links = False
    return h.handle(html)


class CustomAnymailMessage(AnymailMessage):
    def __init__(self, stats_category, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats_category = stats_category

    def send(self, *args, **kwargs):
        try:
            self._send_or_retry(*args, **kwargs)
            stats.email_sent(recipient_count=len(self.to), category=self.stats_category)
        except Exception as exception:
            stats.email_error(recipient_count=len(self.to), category=self.stats_category)
            raise exception

    def _send_or_retry(self, *args, **kwargs):
        attempts_left = 3
        while True:
            attempts_left -= 1
            try:
                return super().send(*args, **kwargs)
            except AnymailAPIError:
                if attempts_left == 0:
                    # all retries exhausted, let's forward the exception
                    raise
                stats.email_retry(recipient_count=len(self.to), category=self.stats_category)


def prepare_email(
    template,
    user=None,
    group=None,
    context=None,
    to=None,
    language=None,
    unsubscribe_url=None,
    **kwargs,
):
    context = dict(context) if context else {}
    tz = kwargs.pop('tz', timezone.utc)

    default_context = {
        'site_name': settings.SITE_NAME,
        'hostname': settings.HOSTNAME,
    }

    if user:
        default_context.update({
            'user': user,
            'user_display_name': user.get_full_name(),
        })

    if group:
        default_context.update({'group_name': group.name})

    # Merge context, but fail if a default key was redefined
    redefined_keys = set(default_context.keys()).intersection(context.keys())
    if len(redefined_keys) > 0:
        raise Exception('email context should not redefine defaults: ' + ', '.join(redefined_keys))
    context.update(default_context)

    if 'header_image' not in context:
        context['header_image'] = group_photo_or_karrot_logo_url(context.get('group', None))

    if not to:
        if not user:
            raise Exception('Do not know who to send the email to, no "user" or "to" field')
        to = [user.email]

    if isinstance(to, str):
        to = [to]

    if user and not language:
        language = user.language

    subject, text_content, html_content = prepare_email_content(template, context, tz, language)

    # add group prefix to subject
    if group:
        subject = f"[{group.name}] {subject}"

    if 'from_email' in kwargs:
        from_email = kwargs.pop('from_email')
        # add the via bit
        from_email = f"{from_email} via {settings.SITE_NAME}"
    else:
        from_email = formataddr((settings.SITE_NAME, settings.DEFAULT_FROM_EMAIL))

    headers = {}

    if unsubscribe_url:
        headers.update({
            'List-Unsubscribe': '<{}>'.format(unsubscribe_url),
        })

    message_kwargs = {
        'subject': subject,
        'body': text_content,
        'to': to,
        'from_email': from_email,
        'headers': headers,
        **kwargs,
    }

    email = CustomAnymailMessage(**message_kwargs)

    if html_content:
        email.attach_alternative(html_content, 'text/html')

    return email


def prepare_email_content(template, context, tz, language='en'):
    if not translation.check_for_language(language):
        language = 'en'

    with timezone.override(tz), translation.override(language):

        html_content = None

        try:
            html_template = get_template('{}.html.jinja2'.format(template))
            html_content = html_template.render(context)
        except TemplateDoesNotExist:
            pass

        try:
            text_template = get_template('{}.text.jinja2'.format(template))
            text_content = text_template.render(context)
        except TemplateDoesNotExist:
            if html_content:
                text_content = generate_plaintext_from_html(html_content)
            else:
                raise Exception('Nothing to use for text content, no text or html templates available.')

        subject = render_to_string('{}.subject.jinja2'.format(template), context).replace('\n', '')

        return subject, text_content, html_content


def formataddr(pair, *args, **kwargs):
    # Be nice and limit the length of 'from_email'
    name, email = pair
    name = Truncator(name).chars(num=75)

    return real_formataddr((name, email), *args, **kwargs)
