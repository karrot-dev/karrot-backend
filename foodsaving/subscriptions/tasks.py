from django.db.models import Q
from huey.contrib.djhuey import db_task

from foodsaving.subscriptions.fcm import notify_subscribers
from foodsaving.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from foodsaving.utils import frontend_urls


@db_task()
def notify_message_push_subscribers(message, exclude_users):
    conversation = message.conversation

    subscriptions = PushSubscription.objects.filter(
        Q(user__in=conversation.participants.all()) & ~Q(user__in=exclude_users) & ~Q(user=message.author)
    ).distinct()

    message_title = message.author.display_name
    if conversation.type() == 'group':
        message_title = '{} / {}'.format(conversation.target.name, message_title)

    if message.is_thread_reply():
        click_action = frontend_urls.thread_url(message.thread)
    else:
        click_action = frontend_urls.conversation_url(conversation, message.author)

    fcm_options = {
        'message_title': message_title,
        'message_body': message.content,
        'click_action': click_action,
        # this causes each notification for a given conversation to replace previous notifications
        # fancier would be to make the new notifications show a summary not just the latest message
        'tag': 'conversation:{}'.format(conversation.id)
    }

    android_subscriptions = subscriptions.filter(platform=PushSubscriptionPlatform.ANDROID.value)
    web_subscriptions = subscriptions.filter(platform=PushSubscriptionPlatform.WEB.value)

    notify_subscribers(
        subscriptions=android_subscriptions, fcm_options={
            **fcm_options,
            'message_icon': 'icon_push',
        }
    )

    notify_subscribers(
        subscriptions=web_subscriptions, fcm_options={
            **fcm_options,
            'message_icon': frontend_urls.logo_url(),
        }
    )
