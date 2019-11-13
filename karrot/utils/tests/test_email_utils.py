import os
import pathlib
from shutil import copyfile

import pytz
from django.test import TestCase
from django.utils import timezone, translation

import karrot.groups.emails
import karrot.invitations.emails
import karrot.users.emails
from config import settings
from karrot.groups.factories import GroupFactory
from karrot.invitations.models import Invitation
from karrot.userauth.models import VerificationCode
from karrot.users.factories import UserFactory
from karrot.utils.email_utils import time_filter, date_filter, generate_plaintext_from_html, prepare_email
from karrot.utils.frontend_urls import group_photo_url, karrot_logo_url


class TestEmailUtils(TestCase):
    def setUp(self):
        self.group = GroupFactory()
        self.user = UserFactory()

    def test_raises_exception_on_redefined_context(self):
        user = UserFactory()
        with self.assertRaisesMessage(Exception, 'email context should not redefine defaults: user'):
            prepare_email(
                template='accountdelete_success',
                user=user,
                context={
                    'user': user,
                },
            )

    def test_emailinvitation(self):
        invitation = Invitation.objects.create(email='bla@bla.com', group=self.group, invited_by=self.user)
        email = karrot.invitations.emails.prepare_emailinvitation_email(invitation)

        self.assertEqual(len(email.alternatives), 1)
        html, mimetype = email.alternatives[0]

        self.assertEqual(mimetype, 'text/html')
        self.assertEqual(email.to[0], 'bla@bla.com')
        self.assertIn(self.group.name, html)
        self.assertIn(self.user.display_name, html)
        self.assertIn(str(invitation.token), html)
        self.assertIn('/#/signup', html)
        self.assertIn(settings.HOSTNAME, html)
        self.assertNotIn('&amp;', email.body)

    def test_signup(self):
        verification_code = VerificationCode.objects.get(user=self.user, type=VerificationCode.EMAIL_VERIFICATION)
        email = karrot.users.emails.prepare_signup_email(
            user=self.user,
            verification_code=verification_code,
        )
        self.assertEqual(email.to[0], self.user.unverified_email)

        self.assertEqual(len(email.alternatives), 1)
        html, mimetype = email.alternatives[0]

        self.assertEqual(mimetype, 'text/html')
        self.assertIn(settings.HOSTNAME, html)
        self.assertIn(verification_code.code, html)

        self.assertIn('/#/email/verify', html)
        self.assertIn(settings.HOSTNAME, html)
        self.assertIn(verification_code.code, html)

    def test_mailverification(self):
        verification_code = VerificationCode.objects.get(user=self.user)
        email = karrot.users.emails.prepare_signup_email(self.user, verification_code)
        html, mimetype = email.alternatives[0]

        self.assertEqual(mimetype, 'text/html')
        self.assertEqual(len(email.alternatives), 1)
        self.assertEqual(email.to[0], self.user.unverified_email)
        self.assertIn(settings.HOSTNAME, html)
        self.assertIn(verification_code.code, html)

    def test_default_header_image(self):
        email = karrot.groups.emails.prepare_user_inactive_in_group_email(self.user, self.group)
        html, _ = email.alternatives[0]
        self.assertIn(karrot_logo_url(), html)

    def test_custom_header_image(self):
        pathlib.Path(settings.MEDIA_ROOT).mkdir(exist_ok=True)
        copyfile(
            os.path.join(os.path.dirname(__file__), './photo.jpg'), os.path.join(settings.MEDIA_ROOT, 'photo.jpg')
        )
        self.group.photo = 'photo.jpg'
        self.group.save()

        email = karrot.groups.emails.prepare_user_inactive_in_group_email(self.user, self.group)
        html, _ = email.alternatives[0]
        self.assertIn(group_photo_url(self.group), html)


class TestHTMLToPlainText(TestCase):
    def test_does_not_split_links(self):
        # token that causes html2text to make a line break if wrap_links option is not set
        token = '4522e1fa-9827-44ec-bf76-f7fa8fb132ff'
        url = 'http://localhost:8080/#/signup?invite={}&email=please%40join.com'.format(token)
        html = '<a href="{}">some link</a>'.format(url)
        text = generate_plaintext_from_html(html)
        self.assertIn(url, text)


class TestJinjaFilters(TestCase):
    def test_time_filter_uses_timezone(self):
        hour = 5
        datetime = timezone.now().replace(
            tzinfo=pytz.utc,
            hour=hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        tz = pytz.timezone('Europe/Berlin')
        offset_hours = int(tz.utcoffset(datetime.utcnow()).total_seconds() / 3600)
        with timezone.override(tz), translation.override('en'):
            val = time_filter(datetime)
            self.assertEqual(val, '{}:00 AM'.format(hour + offset_hours))

    def test_date_filter_uses_timezone(self):
        # 11pm on Sunday UTC
        datetime = timezone.now().replace(
            tzinfo=pytz.utc,
            year=2018,
            month=3,
            day=11,
            hour=23,
            minute=0,
            second=0,
            microsecond=0,
        )
        with timezone.override(pytz.timezone('Europe/Berlin')), translation.override('en'):
            # ... is Monday in Berlin
            val = date_filter(datetime)
            self.assertIn('Monday', val)
