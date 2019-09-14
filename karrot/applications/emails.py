from config import settings
from karrot.conversations.models import Conversation
from karrot.utils.email_utils import prepare_email, formataddr
from karrot.utils.frontend_urls import group_wall_url, application_url, \
    applications_url, group_edit_url, new_application_unsubscribe_url
from karrot.webhooks.utils import make_local_part


def prepare_new_application_notification_email(user, application):
    applicant = application.user
    conversation = Conversation.objects.get_for_target(application)

    reply_to_name = applicant.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((applicant.display_name, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = new_application_unsubscribe_url(user, application)

    return prepare_email(
        template='new_application',
        from_email=from_email,
        user=user,
        tz=application.group.timezone,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'applicant': applicant,
            'group': application.group,
            'questions': application.questions_rendered(),
            'answers': application.answers_rendered(),
            'conversation_url': application_url(application),
            'mute_url': unsubscribe_url,
            'new_application_unsubscribe_url': unsubscribe_url,
            'applications_url': applications_url(application.group),
            'group_edit_url': group_edit_url(application.group),
        }
    )


def prepare_application_accepted_email(application):
    return prepare_email(
        template='application_accepted',
        user=application.user,
        tz=application.group.timezone,
        context={
            'group': application.group,
            'group_url': group_wall_url(application.group)
        }
    )


def prepare_application_declined_email(application):
    return prepare_email(
        template='application_declined',
        user=application.user,
        tz=application.group.timezone,
        context={
            'group': application.group,
        },
    )
