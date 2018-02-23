from anymail.message import AnymailMessage
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string, get_template

from config import settings


def send_email(template, user, context, to=None):
    context = {
        **context,
        'user': user,
        'user_display_name': user.get_full_name(),
        'site_name': settings.SITE_NAME,
    }

    email = AnymailMessage(
        subject=render_to_string('{}.subject.jinja2'.format(template), context).replace('\n', ''),
        body=render_to_string('{}.text.jinja2'.format(template), context),
        to=[to if to is not None else user.email],
        from_email=settings.DEFAULT_FROM_EMAIL,
        track_clicks=False,
        track_opens=False
    )

    try:
        html_template = get_template('{}.html.jinja2'.format(template))
        html_content = html_template.render(context)
        email.attach_alternative(html_content, 'text/html')
    except TemplateDoesNotExist:
        pass

    email.send()
