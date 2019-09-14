from config import settings
from karrot.conversations.models import Conversation
from karrot.utils.email_utils import prepare_email, formataddr
from karrot.utils.frontend_urls import conflict_resolution_unsubscribe_url, issue_url
from karrot.webhooks.utils import make_local_part


def prepare_new_conflict_resolution_email_to_affected_user(issue):
    created_by = issue.created_by
    conversation = Conversation.objects.get_for_target(issue)
    voting = issue.latest_voting()
    user = issue.affected_user

    reply_to_name = created_by.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((created_by.display_name, settings.DEFAULT_FROM_EMAIL))

    this_issue_url = issue_url(issue)

    return prepare_email(
        template='new_conflict_resolution_affected_user',
        from_email=from_email,
        user=user,
        tz=issue.group.timezone,
        reply_to=[reply_to],
        context={
            'created_by': created_by,
            'topic': issue.topic_rendered(),
            'conversation_url': this_issue_url,
            'issue_url': this_issue_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_new_conflict_resolution_email(user, issue):
    created_by = issue.created_by
    affected_user = issue.affected_user
    conversation = Conversation.objects.get_for_target(issue)
    voting = issue.latest_voting()

    reply_to_name = created_by.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((created_by.display_name, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = conflict_resolution_unsubscribe_url(user, issue)
    this_issue_url = issue_url(issue)

    return prepare_email(
        template='new_conflict_resolution',
        from_email=from_email,
        user=user,
        tz=issue.group.timezone,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'created_by': created_by,
            'affected_user': affected_user,
            'topic': issue.topic_rendered(),
            'conversation_url': this_issue_url,
            'unsubscribe_url': unsubscribe_url,
            'issue_url': this_issue_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_conflict_resolution_continued_email(user, issue):
    affected_user = issue.affected_user
    voting = issue.latest_voting()

    unsubscribe_url = conflict_resolution_unsubscribe_url(user, issue)
    this_issue_url = issue_url(issue)

    return prepare_email(
        template='conflict_resolution_continued',
        user=user,
        tz=issue.group.timezone,
        context={
            'affected_user': affected_user,
            'unsubscribe_url': unsubscribe_url,
            'issue_url': this_issue_url,
            'expires_at': voting.expires_at,
        }
    )


def prepare_conflict_resolution_continued_email_to_affected_user(issue):
    voting = issue.latest_voting()
    user = issue.affected_user

    this_issue_url = issue_url(issue)

    return prepare_email(
        template='conflict_resolution_continued_affected_user',
        user=user,
        tz=issue.group.timezone,
        context={
            'issue_url': this_issue_url,
            'expires_at': voting.expires_at,
        }
    )
