import html
import os
import random
import re
from collections import namedtuple

from dateutil.relativedelta import relativedelta
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotFound
from django.template.loader import render_to_string
from django.template.utils import get_app_template_dirs
from django.utils import timezone

import karrot.applications.emails
import karrot.conversations.emails
import karrot.invitations.emails
import karrot.issues.emails
import karrot.users.emails
from config import settings
from karrot.activities.emails import prepare_activity_notification_email, prepare_participant_removed_email
from karrot.activities.models import Activity, ActivitySeries
from karrot.applications.factories import ApplicationFactory
from karrot.applications.models import Application
from karrot.conversations.emails import prepare_mention_notification
from karrot.conversations.models import Conversation, ConversationMessage
from karrot.groups.emails import (
    prepare_group_summary_data,
    prepare_group_summary_emails,
    prepare_user_became_editor_email,
    prepare_user_inactive_in_group_email,
    prepare_user_removal_from_group_email,
)
from karrot.groups.models import Group
from karrot.invitations.models import Invitation
from karrot.issues.factories import IssueFactory
from karrot.offers.emails import prepare_new_offer_notification_email
from karrot.offers.factories import OfferFactory
from karrot.offers.models import Offer
from karrot.users.factories import VerifiedUserFactory
from karrot.users.models import User
from karrot.utils.tests.fake import faker

basedir = os.path.abspath(os.path.join(settings.BASE_DIR, "karrot"))

MockVerificationCode = namedtuple("VerificationCode", ["code"])


def random_user(group=None):
    if group:
        return group.members.order_by("?").first()
    return User.objects.order_by("?").first()


def random_group():
    return shuffle_groups().first()


def shuffle_groups():
    return Group.objects.order_by("?")


def random_issue():
    return IssueFactory(group=random_group(), created_by=random_user(), affected_user=random_user())


def random_conversation():
    return Conversation.objects.order_by("?").first()


def random_message():
    conversation = ConversationMessage.objects.order_by("?").first().conversation
    return conversation.messages.exclude_replies().first()


def random_messages():
    conversation = ConversationMessage.objects.order_by("?").first().conversation
    messages = conversation.messages.exclude_replies().all()
    if len(messages) > 5:
        messages = messages[:4]
    return messages


def random_reply():
    return ConversationMessage.objects.only_replies().order_by("?").first()


def pseudo_verification_code():
    return MockVerificationCode(code="0123456789012345678901234567890123456789")


def get_or_create_application():
    application = Application.objects.order_by("?").first()

    if application is None:
        new_user = VerifiedUserFactory()
        group = random_group()
        if group.application_questions == "":
            group.application_questions = faker.text()
            group.save()
        application = ApplicationFactory(
            group=group,
            user=new_user,
        )

    return application


def get_or_create_offer():
    offer = Offer.objects.order_by("?").first()

    if offer is None:
        user = VerifiedUserFactory()
        group = random_group()
        image_path = os.path.join(os.path.dirname(__file__), "./offer.jpg")
        offer = OfferFactory(group=group, user=user, images=[image_path])

    return offer


def get_or_create_mention():
    group = random_group()
    author = random_user(group)
    mentioned_user = random_user(group)
    conversation = group.conversation

    # insert a mention into some faker text
    parts = faker.text().split(" ")
    parts.insert(random.randint(0, len(parts)), f"@{mentioned_user.username}")
    content = " ".join(parts)

    message = conversation.messages.create(author=author, content=content)
    return message.mentions.first()


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
                group=group, invited_by=invited_by, email="exampleinvitation@foo.com"
            )
        return karrot.invitations.emails.prepare_emailinvitation_email(invitation)

    def new_application(self):
        application = get_or_create_application()
        member = application.group.members.first()
        return karrot.applications.emails.prepare_new_application_notification_email(member, application)

    def new_conflict_resolution(self):
        issue = random_issue()
        return karrot.issues.emails.prepare_new_conflict_resolution_email(issue.created_by, issue)

    def new_conflict_resolution_affected_user(self):
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
            "No emails were generated, you need at least one verified user in your db, and some activity data..."
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

    def activity_notification(self):
        group = random_group()
        user = random_user(group)

        activity1 = Activity.objects.order_by("?").first()
        activity2 = Activity.objects.order_by("?").first()
        activity3 = Activity.objects.order_by("?").first()
        activity4 = Activity.objects.order_by("?").first()

        localtime = timezone.localtime()

        return prepare_activity_notification_email(
            user=user,
            group=user.groups.first(),
            tonight_date=localtime,
            tomorrow_date=localtime + relativedelta(days=1),
            tonight_user=[activity1, activity2],
            tonight_empty=[activity3, activity4],
            tonight_not_full=[activity4],
            tomorrow_user=[activity2],
            tomorrow_empty=[activity3],
            tomorrow_not_full=[activity4],
        )

    def participant_removed(self):
        group = random_group()
        user = random_user(group)
        removed_by = random_user(group)

        series = ActivitySeries.objects.order_by("?").first()
        activities = Activity.objects.order_by("?")[:3]

        return prepare_participant_removed_email(
            user=user,
            place=series.place,
            activities=activities,  # not exactly what the template gets passed in real-life, but close enough
            removed_by=removed_by,
            message=faker.text(),
        )

    def user_became_editor(self):
        return prepare_user_became_editor_email(user=random_user(), group=random_group())

    def user_inactive_in_group(self):
        return prepare_user_inactive_in_group_email(user=random_user(), group=random_group())

    def user_removal_from_group(self):
        return prepare_user_removal_from_group_email(user=random_user(), group=random_group())

    def new_offer(self):
        return prepare_new_offer_notification_email(user=random_user(), offer=get_or_create_offer())

    def mention_notification(self):
        return prepare_mention_notification(get_or_create_mention())


handlers = Handlers()


def list_templates(request):
    template_dirs = [str(path) for path in get_app_template_dirs("templates") if re.match(r".*/karrot/.*", str(path))]

    # collect template files
    template_files = {}
    for directory in template_dirs:
        for directory, _dirnames, filenames in os.walk(directory):
            relative_dir = directory[len(basedir) + 1 :]
            for filename in filenames:
                if re.match(r".*\.jinja2$", filename) and not re.match(r".*\.nopreview\.jinja2$", filename):
                    path = os.path.join(relative_dir, filename)

                    # strip out anything past the first dot for the name
                    name = re.sub(r"\..*$", "", os.path.basename(path))

                    if name != "template_preview_list":
                        formats = []

                        for _idx, s in enumerate(["subject", "text", "html"]):
                            if os.path.isfile(f"{os.path.join(directory, name)}.{s}.jinja2"):
                                formats.append(s)
                            elif s == "text":
                                formats.append("autotext")

                        # only include if some formats were defined (even empty ones would end up with autotext...)
                        if len(formats) > 1:
                            formats.append("raw")
                            template_files[name] = formats

    templates = {}

    for name in dir(handlers):
        if name.startswith("_"):
            continue
        templates[name] = {
            "name": name,
            "has_handler": True,  # because we are listing the handlers :)
            "formats": template_files.get(name, []),
        }

    missing_handlers = [name for name in template_files.keys() if name not in templates]

    return HttpResponse(
        render_to_string(
            "template_preview_list.jinja2",
            {
                "templates": templates.values(),
                "missing_handlers": missing_handlers,
                "views_filename": __file__,
            },
        )
    )


def show_template(request):
    name = request.GET.get("name")
    format = request.GET.get("format", "html")

    if name is None:
        return HttpResponseBadRequest("must specify template name")

    has_handler = name in dir(handlers)

    if not has_handler:
        return HttpResponseNotFound(
            f"Please setup a handler for the <strong>{name}</strong> in <strong>{__file__}</strong>"
        )

    email = getattr(handlers, name)()

    if format == "html":
        html_content = None
        for content, mimetype in email.alternatives:
            if mimetype == "text/html":
                html_content = content

        if html_content is None:
            return HttpResponseNotFound(f"{name} does not have html content")

        return HttpResponse(html_content)

    elif format == "text" or format == "autotext":
        return HttpResponse(f"<pre>{email.body}</pre>")

    elif format == "subject":
        return HttpResponse(f"<pre>{email.subject}</pre>")

    elif format == "raw":
        return HttpResponse(f"<pre>{html.escape(email.message().as_string())}</pre>")
