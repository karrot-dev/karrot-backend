from babel.dates import format_date, format_time
from django.utils import translation, timezone
from django.utils.text import Truncator
from django.utils.translation import ugettext as _

from config import settings
from foodsaving.utils.email_utils import prepare_email, formataddr
from foodsaving.utils.frontend_urls import (
    group_wall_url, conversation_unsubscribe_url, pickup_detail_url, user_detail_url, group_application_url,
    thread_url, thread_unsubscribe_url, conflict_resolution_url
)
from foodsaving.webhooks.api import make_local_part


def author_names(messages):
    return ', '.join(set(message.author.display_name for message in messages))


def prepare_conversation_message_notification(user, messages):
    first_message = messages[0]
    type = first_message.conversation.type()

    if type == 'group' and first_message.is_thread_reply():
        return prepare_group_thread_message_notification(user, messages)
    if type == 'pickup':
        return prepare_pickup_conversation_message_notification(user, messages)
    if type == 'application':
        return prepare_group_application_message_notification(user, messages)
    if type == 'issue':
        return prepare_issue_message_notification(user, messages)
    if type == 'private':
        return prepare_private_user_conversation_message_notification(user, messages)
    raise Exception('Cannot send message notification because conversation doesn\'t have a known type')


def prepare_group_thread_message_notification(user, messages):
    first_message = messages[0]
    conversation = first_message.conversation
    group = conversation.find_group()
    thread = first_message.thread

    thread_text_beginning = Truncator(thread.content).chars(num=60)

    from_text = author_names(messages)
    reply_to_name = thread.author.display_name
    conversation_name = thread_text_beginning

    local_part = make_local_part(conversation, user, thread)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = thread_unsubscribe_url(user, group, thread)

    return prepare_email(
        template='thread_message_notification',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'messages': messages,
            'conversation_name': conversation_name,
            'thread_author': thread.author,
            'thread_message_content': thread.content_rendered(truncate_words=40),
            'thread_url': thread_url(thread),
            'mute_url': unsubscribe_url,
        }
    )


def prepare_group_conversation_message_notification(user, message):
    conversation = message.conversation
    group = conversation.target

    from_text = message.author.display_name
    reply_to_name = group.name
    conversation_name = group.name

    local_part = make_local_part(conversation, user, message)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = conversation_unsubscribe_url(user, group=group, conversation=conversation)

    return prepare_email(
        template='conversation_message_notification',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'messages': [message],
            'conversation_name': conversation_name,
            'conversation_url': group_wall_url(group),
            'mute_url': unsubscribe_url,
        }
    )


def prepare_pickup_conversation_message_notification(user, messages):
    first_message = messages[0]
    conversation = first_message.conversation
    pickup = conversation.target
    group_tz = pickup.store.group.timezone

    language = user.language

    if not translation.check_for_language(language):
        language = 'en'

    with translation.override(language):
        with timezone.override(group_tz):
            weekday = format_date(
                pickup.date.lower.astimezone(timezone.get_current_timezone()),
                'EEEE',
                locale=translation.to_locale(language),
            )
            time = format_time(
                pickup.date.lower,
                format='short',
                locale=translation.to_locale(language),
                tzinfo=timezone.get_current_timezone(),
            )
            date = format_date(
                pickup.date.lower.astimezone(timezone.get_current_timezone()),
                format='long',
                locale=translation.to_locale(language),
            )

            long_date = '{} {}, {}'.format(weekday, time, date)
            short_date = '{} {}'.format(weekday, time)

            reply_to_name = _('Pickup %(date)s') % {
                'date': short_date,
            }
            conversation_name = _('Pickup %(date)s') % {
                'date': long_date,
            }

            from_text = author_names(messages)

            local_part = make_local_part(conversation, user)
            reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
            from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

            unsubscribe_url = conversation_unsubscribe_url(user, group=pickup.store.group, conversation=conversation)

            return prepare_email(
                template='conversation_message_notification',
                from_email=from_email,
                user=user,
                reply_to=[reply_to],
                unsubscribe_url=unsubscribe_url,
                context={
                    'messages': messages,
                    'conversation_name': conversation_name,
                    'conversation_url': pickup_detail_url(pickup),
                    'mute_url': unsubscribe_url,
                }
            )


def prepare_private_user_conversation_message_notification(user, messages):
    first_message = messages[0]
    conversation = first_message.conversation
    author = first_message.author
    reply_to_name = author.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((author.display_name, settings.DEFAULT_FROM_EMAIL))

    unsubscribe_url = conversation_unsubscribe_url(author, conversation=conversation)

    return prepare_email(
        template='conversation_message_notification',
        from_email=from_email,
        user=user,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'messages': messages,
            'conversation_name': author.display_name,
            'conversation_url': user_detail_url(author),
            'mute_url': unsubscribe_url,
        }
    )


def prepare_group_application_message_notification(user, messages):
    first_message = messages[0]
    conversation = first_message.conversation
    application = conversation.target

    language = user.language

    if not translation.check_for_language(language):
        language = 'en'

    with translation.override(language):
        reply_to_name = application.user.display_name
        conversation_name = _('New message in application of %(user_name)s to %(group_name)s') % {
            'user_name': application.user.display_name,
            'group_name': application.group.name,
        }
        if application.user == user:
            conversation_name = _('New message in your application to %(group_name)s') % {
                'group_name': application.group.name
            }

        from_text = author_names(messages)

        local_part = make_local_part(conversation, user)
        reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
        from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

        unsubscribe_url = conversation_unsubscribe_url(user, group=application.group, conversation=conversation)

        return prepare_email(
            template='conversation_message_notification',
            from_email=from_email,
            user=user,
            reply_to=[reply_to],
            unsubscribe_url=unsubscribe_url,
            context={
                'messages': messages,
                'conversation_name': conversation_name,
                'conversation_url': group_application_url(application),
                'mute_url': unsubscribe_url,
            }
        )


def prepare_issue_message_notification(user, messages):
    first_message = messages[0]
    conversation = first_message.conversation
    author = first_message.author
    reply_to_name = author.display_name
    issue = conversation.target

    language = user.language

    if not translation.check_for_language(language):
        language = 'en'

    with translation.override(language):
        conversation_name = _('New message in conflict resolution in %(group_name)s') % {
            'group_name': issue.group.name,
        }

        from_text = author_names(messages)

        local_part = make_local_part(conversation, user)
        reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
        from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

        unsubscribe_url = conversation_unsubscribe_url(user, group=issue.group, conversation=conversation)

        return prepare_email(
            template='conversation_message_notification',
            from_email=from_email,
            user=user,
            reply_to=[reply_to],
            unsubscribe_url=unsubscribe_url,
            context={
                'messages': messages,
                'conversation_name': conversation_name,
                'conversation_url': conflict_resolution_url(issue),
                'mute_url': unsubscribe_url,
            }
        )
