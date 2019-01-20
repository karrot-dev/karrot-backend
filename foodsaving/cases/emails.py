from config import settings
from foodsaving.conversations.models import Conversation
from foodsaving.utils.email_utils import prepare_email, formataddr
from foodsaving.utils.frontend_urls import conflict_resolution_unsubscribe_url, conflict_resolution_url
from foodsaving.webhooks.api import make_local_part


def prepare_new_conflict_resolution_email_to_affected_user(case):
    created_by = case.created_by
    conversation = Conversation.objects.get_for_target(case)
    voting = case.latest_voting()
    user = case.affected_user

    reply_to_name = created_by.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((created_by.display_name, settings.DEFAULT_FROM_EMAIL))

    case_url = conflict_resolution_url(case)

    return prepare_email(
        template='new_conflict_resolution_case_affected_user',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        context={
            'created_by': created_by,
            'topic': case.topic_rendered(),
            'conversation_url': case_url,
            'conflict_resolution_url': case_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_new_conflict_resolution_email(user, case):
    created_by = case.created_by
    affected_user = case.affected_user
    conversation = Conversation.objects.get_for_target(case)
    voting = case.latest_voting()

    reply_to_name = created_by.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((created_by.display_name, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = conflict_resolution_unsubscribe_url(user, case)
    case_url = conflict_resolution_url(case)

    return prepare_email(
        template='new_conflict_resolution_case',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'created_by': created_by,
            'affected_user': affected_user,
            'topic': case.topic_rendered(),
            'conversation_url': case_url,
            'unsubscribe_url': unsubscribe_url,
            'conflict_resolution_url': case_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_conflict_resolution_case_continued_email(user, case):
    affected_user = case.affected_user
    voting = case.latest_voting()

    unsubscribe_url = conflict_resolution_unsubscribe_url(user, case)
    case_url = conflict_resolution_url(case)

    return prepare_email(
        template='conflict_resolution_case_continued',
        user=user,
        context={
            'affected_user': affected_user,
            'unsubscribe_url': unsubscribe_url,
            'conflict_resolution_url': case_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_conflict_resolution_case_continued_email_to_affected_user(case):
    voting = case.latest_voting()
    user = case.affected_user

    case_url = conflict_resolution_url(case)

    return prepare_email(
        template='conflict_resolution_case_continued_affected_user',
        user=user,
        context={
            'conflict_resolution_url': case_url,
            'expires_at': voting.expires_at,
        }
    )
