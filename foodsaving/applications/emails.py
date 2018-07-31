from email.utils import formataddr

from config import settings
from foodsaving.conversations.models import Conversation
from foodsaving.utils.email_utils import prepare_email
from foodsaving.utils.frontend_urls import group_wall_url, group_settings_url, group_application_url, \
    group_application_mute_url, group_applications_url, group_edit_url
from foodsaving.webhooks.api import make_local_part


def prepare_new_application_notification_email(user, application):
    applicant = application.user
    conversation = Conversation.objects.get_for_target(application)

    reply_to_name = applicant.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((applicant.display_name, settings.DEFAULT_FROM_EMAIL))

    return prepare_email(
        'new_application',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        context={
            'applicant': applicant,
            'group': application.group,
            'questions': application.questions_rendered(),
            'answers': application.answers_rendered(),
            'conversation_url': group_application_url(application),
            'mute_url': group_application_mute_url(application, conversation),
            'settings_url': group_settings_url(application.group),
            'group_applications_url': group_applications_url(application.group),
            'group_edit_url': group_edit_url(application.group),
        }
    )


def prepare_application_accepted_email(application):
    return prepare_email(
        'application_accepted',
        user=application.user,
        context={
            'group': application.group,
            'group_url': group_wall_url(application.group)
        }
    )


def prepare_application_declined_email(application):
    return prepare_email(
        'application_declined', user=application.user, context={
            'group': application.group,
        }
    )
