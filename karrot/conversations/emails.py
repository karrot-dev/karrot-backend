import pytz
from babel.dates import format_date, format_time
from django.utils import translation, timezone
from django.utils.text import Truncator
from django.utils.translation import gettext as _

from config import settings
from karrot.utils.email_utils import prepare_email, formataddr
from karrot.utils.frontend_urls import (
    group_wall_url, conversation_unsubscribe_url, activity_detail_url, user_detail_url, application_url, thread_url,
    thread_unsubscribe_url, issue_url, place_wall_url, offer_url
)
from karrot.webhooks.utils import make_local_part


def author_names(messages):
    return ', '.join(set(message.author.display_name for message in messages))


def prepare_conversation_message_notification(user, messages):
    first_message = messages[0]
    type = first_message.conversation.type()

    if first_message.is_thread_reply():
        return prepare_thread_message_notification(user, messages)
    if type == 'activity':
        return prepare_activity_conversation_message_notification(user, messages)
    if type == 'application':
        return prepare_application_message_notification(user, messages)
    if type == 'issue':
        return prepare_issue_message_notification(user, messages)
    if type == 'offer':
        return prepare_offer_message_notification(user, messages)
    if type == 'private':
        return prepare_private_user_conversation_message_notification(user, messages)
    raise Exception('Cannot send message notification because conversation doesn\'t have a known type')


def prepare_thread_message_notification(user, messages):
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
        tz=group.timezone,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'messages': messages,
            'conversation_name': conversation_name,
            'thread_author': thread.author,
            'thread_message_content': thread.content_rendered(truncate_words=40),
            'thread_url': thread_url(thread),
            'mute_url': unsubscribe_url,
        },
        stats_category='thread_message',
    )


def target_from_messages(messages):
    first_message = messages[0]
    conversation = first_message.conversation
    return conversation.target


def language_for_user(user):
    language = user.language

    if not translation.check_for_language(language):
        language = 'en'

    return language


def prepare_message_notification(
    user,
    messages,
    *,
    conversation_name,
    conversation_url,
    stats_category,
    group=None,
    reply_to_name=None,
):
    first_message = messages[0]
    conversation = first_message.conversation
    author = first_message.author

    if group:
        tz = group.timezone
    elif user.current_group:
        tz = user.current_group.timezone
    else:
        # default, I guess most groups are not so far from this timezone...
        tz = pytz.timezone('Europe/Berlin')

    if reply_to_name is None:
        reply_to_name = author.display_name

    with translation.override(language_for_user(user)):
        from_text = author_names(messages)

        # If the conversation supports threads, replies should go into a thread, not the main conversation
        thread = first_message if conversation.target and conversation.target.conversation_supports_threads else None

        local_part = make_local_part(conversation, user, thread)
        reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
        from_email = formataddr((from_text, settings.DEFAULT_FROM_EMAIL))

        unsubscribe_url = conversation_unsubscribe_url(user, group=group, conversation=conversation)

        return prepare_email(
            template='conversation_message_notification',
            from_email=from_email,
            user=user,
            tz=tz,
            reply_to=[reply_to],
            unsubscribe_url=unsubscribe_url,
            context={
                'messages': messages,
                'conversation_name': conversation_name,
                'conversation_url': conversation_url,
                'mute_url': unsubscribe_url,
            },
            stats_category=stats_category,
        )


def prepare_group_conversation_message_notification(user, message):
    conversation = message.conversation
    group = conversation.target
    reply_to_name = group.name
    conversation_name = group.name
    with translation.override(language_for_user(user)):
        return prepare_message_notification(
            user,
            messages=[message],
            group=group,
            reply_to_name=reply_to_name,
            conversation_name=conversation_name,
            conversation_url=group_wall_url(group),
            stats_category='group_conversation_message'
        )


def prepare_place_conversation_message_notification(user, message):
    conversation = message.conversation
    place = conversation.target
    reply_to_name = place.name
    conversation_name = place.name
    with translation.override(language_for_user(user)):
        return prepare_message_notification(
            user,
            messages=[message],
            group=place.group,
            reply_to_name=reply_to_name,
            conversation_name=conversation_name,
            conversation_url=place_wall_url(place),
            stats_category='place_conversation_message'
        )


def prepare_activity_conversation_message_notification(user, messages):
    activity = target_from_messages(messages)
    language = language_for_user(user)
    with translation.override(language):
        with timezone.override(activity.place.group.timezone):
            weekday = format_date(
                activity.date.start.astimezone(timezone.get_current_timezone()),
                'EEEE',
                locale=translation.to_locale(language),
            )
            time = format_time(
                activity.date.start,
                format='short',
                locale=translation.to_locale(language),
                tzinfo=timezone.get_current_timezone(),
            )
            date = format_date(
                activity.date.start.astimezone(timezone.get_current_timezone()),
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

        return prepare_message_notification(
            user,
            messages,
            group=activity.place.group,
            reply_to_name=reply_to_name,
            conversation_name=conversation_name,
            conversation_url=activity_detail_url(activity),
            stats_category='activity_conversation_message'
        )


def prepare_private_user_conversation_message_notification(user, messages):
    with translation.override(language_for_user(user)):
        first_message = messages[0]
        author = first_message.author
        return prepare_message_notification(
            user,
            messages,
            conversation_name=author.display_name,
            conversation_url=user_detail_url(author),
            stats_category='private_conversation_message'
        )


def prepare_application_message_notification(user, messages):
    application = target_from_messages(messages)
    with translation.override(language_for_user(user)):
        reply_to_name = application.user.display_name
        if application.user == user:
            conversation_name = _('New message in your application to %(group_name)s') % {
                'group_name': application.group.name
            }
        else:
            conversation_name = _('New message in application of %(user_name)s to %(group_name)s') % {
                'user_name': application.user.display_name,
                'group_name': application.group.name,
            }
        return prepare_message_notification(
            user,
            messages,
            reply_to_name=reply_to_name,
            group=application.group,
            conversation_name=conversation_name,
            conversation_url=application_url(application),
            stats_category='application_message'
        )


def prepare_issue_message_notification(user, messages):
    issue = target_from_messages(messages)
    with translation.override(language_for_user(user)):
        return prepare_message_notification(
            user,
            messages,
            group=issue.group,
            conversation_name=_('New message in conflict resolution in %(group_name)s') % {
                'group_name': issue.group.name,
            },
            conversation_url=issue_url(issue),
            stats_category='issue_message'
        )


def prepare_offer_message_notification(user, messages):
    offer = target_from_messages(messages)
    with translation.override(language_for_user(user)):
        return prepare_message_notification(
            user,
            messages,
            group=offer.group,
            conversation_name=_('New message for offer %(offer_name)s in %(group_name)s') % {
                'offer_name': offer.name,
                'group_name': offer.group.name,
            },
            conversation_url=offer_url(offer),
            stats_category='offer_message'
        )
