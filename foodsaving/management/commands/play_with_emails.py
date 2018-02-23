from anymail.message import AnymailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _

from config import settings
from foodsaving.users.models import User
from foodsaving.utils.email import send_email


class Command(BaseCommand):

    def handle(self, *args, **options):

        user = User.objects.first()

        send_email('mailverification', user, {
            'url': '{hostname}/#/verify-mail?key={code}'.format(
                hostname=settings.HOSTNAME,
                code='ESFOIJSEFOIJOI'
            )
        })

        #
        #
        # email = AnymailMessage(
        #     subject=render_to_string('mailverification.subject.jinja2').replace('\n', ''),
        #     body=render_to_string('mailverification.text.jinja2', context),
        #     to=[user.unverified_email],
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     track_clicks=False,
        #     track_opens=False
        # )
        #
        # html_content = render_to_string('mailverification.html.jinja2', context)
        # email.attach_alternative(html_content, 'text/html')
        #
        # email.send()
        #
        # new_password = User.objects.make_random_password(length=20)
        #
        # AnymailMessage(
        #     subject=_('New password'),
        #     body=_('Here is your new temporary password: {}. ' +
        #            'You can use it to login. Please change it soon.').format(new_password),
        #     to=[user.email],
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     track_clicks=False,
        #     track_opens=False
        # ).send()