import html
import os
import re
from collections import namedtuple

from dateutil.relativedelta import relativedelta
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.template.utils import get_app_template_dirs
from django.utils import timezone

import karrot.applications.emails
import karrot.issues.emails
import karrot.conversations.emails
import karrot.invitations.emails
import karrot.users.emails
from config import settings
from karrot.applications.factories import ApplicationFactory
from karrot.applications.models import Application
from karrot.issues.factories import IssueFactory
from karrot.conversations.models import ConversationMessage
from karrot.groups.emails import prepare_user_inactive_in_group_email, prepare_group_summary_emails, \
    prepare_group_summary_data, prepare_user_became_editor_email, prepare_user_removal_from_group_email
from karrot.groups.models import Group
from karrot.invitations.models import Invitation
from karrot.pickups.emails import prepare_pickup_notification_email
from karrot.pickups.models import PickupDate
from karrot.users.factories import VerifiedUserFactory
from karrot.users.models import User
from karrot.utils.tests.fake import faker

foodsaving_basedir = os.path.abspath(os.path.join(settings.BASE_DIR, 'foodsaving'))

MockVerificationCode = namedtuple('VerificationCode', ['code'])


def random_user():
    return User.objects.order_by('?').first()


def random_group():
    return shuffle_groups().first()


def shuffle_groups():
    return Group.objects.order_by('?')


def random_issue():
    return IssueFactory(group=random_group(), created_by=random_user(), affected_user=random_user())


def random_message():
    conversation = ConversationMessage.objects.order_by('?').first().conversation
    return conversation.messages.exclude_replies().first()


def random_messages():
    conversation = ConversationMessage.objects.order_by('?').first().conversation
    messages = conversation.messages.exclude_replies().all()
    if len(messages) > 5:
        messages = messages[:4]
    return messages


def random_reply():
    return ConversationMessage.objects.only_replies().order_by('?').first()


def pseudo_verification_code():
    return MockVerificationCode(code='0123456789012345678901234567890123456789')


def get_or_create_application():
    application = Application.objects.order_by('?').first()

    if application is None:
        new_user = VerifiedUserFactory()
        group = random_group()
        if group.application_questions == '':
            group.application_questions = faker.text()
            group.save()
        application = ApplicationFactory(
            group=group,
            user=new_user,
        )

    return application


class Handlers:
    def accountdelete_request(self):
        return karrot.users.emails.prepare_accountdelete_request_email(
            user=random_user(), verification_code=pseudo_verification_code()
        )

    def accountdelete_success(self):
        return karrot.users.emails.prepare_accountdelete_success_email(user=random_user())

    def application_accepted(self):
        application = get_or_create_application()
        return karrot.applications.emails.prepare_application_accepted_email(application)

    def application_declined(self):
        application = get_or_create_application()
        return karrot.applications.emails.prepare_application_declined_email(application)

    def changemail_success(self):
        return karrot.users.emails.prepare_changemail_success_email(user=random_user())

    def conflict_resolution_continued(self):
        issue = random_issue()
        return karrot.issues.emails.prepare_conflict_resolution_continued_email(issue.created_by, issue)

    def conflict_resolution_continued_affected_user(self):
        issue = random_issue()
        return karrot.issues.emails.prepare_conflict_resolution_continued_email_to_affected_user(issue)

    def conversation_message_notification(self):
        return karrot.conversations.emails.prepare_group_conversation_message_notification(
            user=random_user(), message=random_message()
        )

    def emailinvitation(self):
        invitation = Invitation.objects.first()
        if invitation is None:
            invited_by = random_user()
            group = Group.objects.first()
            invitation = Invitation.objects.create(
                group=group, invited_by=invited_by, email='exampleinvitation@foo.com'
            )
        return karrot.invitations.emails.prepare_emailinvitation_email(invitation)

    def new_application(self):
        application = get_or_create_application()
        member = application.group.members.first()
        return karrot.applications.emails.prepare_new_application_notification_email(member, application)

    def new_conflict_resolution_issue(self):
        issue = random_issue()
        return karrot.issues.emails.prepare_new_conflict_resolution_email(issue.created_by, issue)

    def new_conflict_resolution_issue_affected_user(self):
        issue = random_issue()
        return karrot.issues.emails.prepare_new_conflict_resolution_email_to_affected_user(issue)

    def group_summary(self):
        from_date = timezone.now() - relativedelta(days=7)
        to_date = from_date + relativedelta(days=7)

        for group in shuffle_groups():
            context = prepare_group_summary_data(group, from_date, to_date)
            summary_emails = prepare_group_summary_emails(group, context)
            if len(summary_emails) == 0:
                continue

            return summary_emails[0]

        raise Exception(
            'No emails were generated, you need at least one verified user in your db, and some activity data...'
        )

    def changemail_request(self):
        return karrot.users.emails.prepare_changemail_request_email(
            user=random_user(), verification_code=pseudo_verification_code()
        )

    def signup(self):
        return karrot.users.emails.prepare_signup_email(
            user=random_user(), verification_code=pseudo_verification_code()
        )

    def thread_message_notification(self):
        return karrot.conversations.emails.prepare_thread_message_notification(
            user=random_user(), messages=[random_reply()]
        )

    def passwordreset_request(self):
        return karrot.users.emails.prepare_passwordreset_request_email(
            user=random_user(), verification_code=pseudo_verification_code()
        )

    def passwordreset_success(self):
        return karrot.users.emails.prepare_passwordreset_success_email(user=random_user())

    def pickup_notification(self):
        user = random_user()

        pickup1 = PickupDate.objects.order_by('?').first()
        pickup2 = PickupDate.objects.order_by('?').first()
        pickup3 = PickupDate.objects.order_by('?').first()
        pickup4 = PickupDate.objects.order_by('?').first()

        localtime = timezone.localtime()

        return prepare_pickup_notification_email(
            user=user,
            group=user.groups.first(),
            tonight_date=localtime,
            tomorrow_date=localtime + relativedelta(days=1),
            tonight_user=[pickup1, pickup2],
            tonight_empty=[pickup3, pickup4],
            tonight_not_full=[pickup4],
            tomorrow_user=[pickup2],
            tomorrow_empty=[pickup3],
            tomorrow_not_full=[pickup4],
        )

    def user_became_editor(self):
        return prepare_user_became_editor_email(user=random_user(), group=random_group())

    def user_inactive_in_group(self):
        return prepare_user_inactive_in_group_email(user=random_user(), group=random_group())

    def user_removal_from_group(self):
        return prepare_user_removal_from_group_email(user=random_user(), group=random_group())


handlers = Handlers()


def list_templates(request):
    template_dirs = [s for s in get_app_template_dirs('templates') if re.match(r'.*/foodsaving/.*', s)]

    template_names = set()

    templates = {}

    for directory in template_dirs:
        for directory, dirnames, filenames in os.walk(directory):
            relative_dir = directory[len(foodsaving_basedir) + 1:]
            for filename in filenames:
                if re.match(r'.*\.jinja2$', filename) and not re.match(r'.*\.nopreview\.jinja2$', filename):
                    path = os.path.join(relative_dir, filename)

                    # strip out anything past the first dot for the name
                    name = re.sub(r'\..*$', '', os.path.basename(path))

                    if name != 'template_preview_list':
                        template_names.add(name)

                        formats = []

                        for idx, s in enumerate(['subject', 'text', 'html']):
                            if os.path.isfile('{}.{}.jinja2'.format(os.path.join(directory, name), s)):
                                formats.append(s)
                            elif s == 'text':
                                formats.append('autotext')

                        # only include if some formats were defined (even empty ones would end up with autotext...)
                        if len(formats) > 1:
                            formats.append('raw')

                            templates[name] = {
                                'name': name,
                                'has_handler': name in dir(handlers),
                                'formats': formats,
                            }

    return HttpResponse(
        render_to_string(
            'template_preview_list.jinja2', {'templates': sorted(templates.values(), key=lambda t: t['name'])}
        )
    )


def show_template(request):
    name = request.GET.get('name')
    format = request.GET.get('format', 'html')

    if name is None:
        return HttpResponseBadRequest('must specify template name')

    has_handler = name in dir(handlers)

    if not has_handler:
        return HttpResponseNotFound(
            'Please setup a handler for the <strong>{}</strong> in <strong>{}</strong>'.format(name, __file__)
        )

    email = getattr(handlers, name)()

    if format == 'html':

        html_content = None
        for content, mimetype in email.alternatives:
            if mimetype == 'text/html':
                html_content = content

        if html_content is None:
            return HttpResponseNotFound('{} does not have html content'.format(name))

        return HttpResponse(html_content)

    elif format == 'text' or format == 'autotext':
        return HttpResponse('<pre>{}</pre>'.format(email.body))

    elif format == 'subject':
        return HttpResponse('<pre>{}</pre>'.format(email.subject))

    elif format == 'raw':
        return HttpResponse('<pre>{}</pre>'.format(html.escape(email.message().as_string())))
