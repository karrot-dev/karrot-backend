from django.core.management import BaseCommand

from karrot.subscriptions.models import WebPushSubscription
from karrot.subscriptions.utils import PushNotifyOptions
from karrot.subscriptions.web_push import notify_subscribers


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--title', help='push message title')
        parser.add_argument('body', metavar='body', type=str, nargs='+', help='body of message')

    def handle(self, *args, **options):
        title = options.get('title', 'Push title')
        body = options.get('body', 'A nice push message')

        options: PushNotifyOptions = {
            "click_action": "https://nicksellen.co.uk",
            "message_title": title,
            "message_body": body,
            "image_url": "/media/__sized__/group_photos/photo_8s1U3PJ-thumbnail-200x200-70.jpg"
        }

        notify_subscribers(
            WebPushSubscription.objects.all(),
            options,
        )
