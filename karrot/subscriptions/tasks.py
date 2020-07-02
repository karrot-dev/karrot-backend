from itertools import groupby

from babel.dates import format_date, format_time
from django.utils import timezone, translation
from django.utils.text import Truncator
from django.utils.translation import gettext as _
from furl import furl
from huey.contrib.djhuey import db_task

from karrot.applications.models import ApplicationStatus
from karrot.groups.models import GroupMembership, GroupNotificationType
from karrot.subscriptions.fcm import notify_subscribers
from karrot.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from karrot.utils import frontend_urls


@db_task()
def notify_message_push_subscribers(message):
    if message.is_thread_reply():
        subscriptions = PushSubscription.objects.filter(
            user__conversationthreadparticipant__thread=message.thread,
            user__conversationthreadparticipant__muted=False,
        )
    else:
        subscriptions = PushSubscription.objects.filter(
            user__conversationparticipant__conversation=message.conversation,
            user__conversationparticipant__muted=False,
        )

    subscriptions = subscriptions.exclude(user=message.author).\
        select_related('user').\
        order_by('user__language').\
        distinct()

    for (language, subscriptions) in groupby(subscriptions, key=lambda subscription: subscription.user.language):
        subscriptions = list(subscriptions)
        notify_message_push_subscribers_with_language(message, subscriptions, language)


def get_message_title(message, language):
    conversation = message.conversation
    author_name = message.author.display_name
    type = conversation.type()

    if message.is_thread_reply():
        thread_start = Truncator(message.thread.content).chars(num=15)
        return '{} / {}'.format(thread_start, author_name)

    if type == 'group':
        return '{} / {}'.format(conversation.target.name, author_name)

    if type == 'place':
        return '{} / {}'.format(conversation.target.name, author_name)

    if type == 'activity':
        activity = conversation.target
        group_tz = activity.place.group.timezone
        with timezone.override(group_tz):
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
        short_date = '{} {}'.format(weekday, time)
        short_name = _('Pickup %(date)s') % {
            'date': short_date,
        }
        return '{} / {}'.format(short_name, author_name)

    if type == 'application':
        application = conversation.target
        applicant_name = application.user.display_name
        if applicant_name == '':
            applicant_name = '(?)'

        emoji = '❓'
        if application.status == ApplicationStatus.ACCEPTED.value:
            emoji = '✅'
        elif application.status == ApplicationStatus.DECLINED.value:
            emoji = '❌'
        elif application.status == ApplicationStatus.WITHDRAWN.value:
            emoji = '🗑️'
        application_title = '{} {}'.format(emoji, applicant_name)

        if message.author == application.user:
            return application_title
        else:
            return '{} / {}'.format(application_title, author_name)

    if type == 'issue':
        issue = conversation.target
        if message.author == issue.affected_user:
            return '☹️ {}'.format(author_name)
        return '☹️ {} / {}'.format(issue.affected_user, author_name)

    if type == 'offer':
        offer = conversation.target
        return '🎁️ {} / {}'.format(offer.name, author_name)

    return author_name


def notify_message_push_subscribers_with_language(message, subscriptions, language):
    conversation = message.conversation

    if not translation.check_for_language(language):
        language = 'en'

    with translation.override(language):
        message_title = get_message_title(message, language)

    if message.is_thread_reply():
        click_action = frontend_urls.thread_url(message.thread)
    else:
        click_action = frontend_urls.conversation_url(conversation, message.author)

    notify_subscribers_by_device(
        subscriptions,
        click_action=click_action,
        fcm_options={
            'message_title': message_title,
            'message_body': Truncator(message.content).chars(num=1000),
            # this causes each notification for a given conversation to replace previous notifications
            # fancier would be to make the new notifications show a summary not just the latest message
            'tag': 'conversation:{}'.format(conversation.id),
        }
    )


@db_task()
def notify_new_offer_push_subscribers(offer):

    users = offer.group.members.filter(
        groupmembership__in=GroupMembership.objects.active().with_notification_type(GroupNotificationType.NEW_OFFER),
    )

    subscriptions = PushSubscription.objects.filter(
        user__in=users,
    ).\
        exclude(user=offer.user). \
        select_related('user'). \
        order_by('user__language'). \
        distinct()

    for (language, subscriptions) in groupby(subscriptions, key=lambda subscription: subscription.user.language):
        subscriptions = list(subscriptions)
        notify_new_offer_push_subscribers_with_language(offer, subscriptions, language)


def notify_new_offer_push_subscribers_with_language(offer, subscriptions, language):
    if not translation.check_for_language(language):
        language = 'en'

    with translation.override(language):
        message_title = '🎁️ {} / {}'.format(offer.name, offer.user.display_name)

    notify_subscribers_by_device(
        subscriptions,
        click_action=frontend_urls.offer_url(offer),
        fcm_options={
            'message_title': message_title,
            'message_body': Truncator(offer.description).chars(num=1000),
            # this causes each notification for a given conversation to replace previous notifications
            # fancier would be to make the new notifications show a summary not just the latest message
            'tag': 'offer:{}'.format(offer.id),
        },
    )


def notify_subscribers_by_device(subscriptions, *, click_action, fcm_options):
    android_subscriptions = [s for s in subscriptions if s.platform == PushSubscriptionPlatform.ANDROID.value]
    web_subscriptions = [s for s in subscriptions if s.platform == PushSubscriptionPlatform.WEB.value]

    notify_subscribers(
        subscriptions=android_subscriptions,
        fcm_options={
            **fcm_options,
            # according to https://github.com/fechanique/cordova-plugin-fcm#send-notification-payload-example-rest-api
            'click_action':
            'FCM_PLUGIN_ACTIVITY',
            'data_message': {
                # we send the route as data - the frontend takes care of the actual routing
                'karrot_route': str(furl(click_action).fragment),
            },
        }
    )

    notify_subscribers(
        subscriptions=web_subscriptions,
        fcm_options={
            **fcm_options,
            'message_icon': frontend_urls.logo_url(),
            'click_action': click_action,
        }
    )
