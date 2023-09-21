import json

from django.conf import settings
from django.core.management import BaseCommand
from pywebpush import webpush

from karrot.subscriptions.models import WebPushSubscription


class Command(BaseCommand):
    def handle(self, *args, **options):

        subscriptions = WebPushSubscription.objects.all()

        for subscription in subscriptions:

            subscription_info = {
                "endpoint": subscription.endpoint,
                "keys": subscription.keys,
            }

            vapid_data = {
                'vapid_private_key': settings.VAPID_PRIVATE_KEY,
                'vapid_claims': {
                    "sub": "mailto:{}".format(settings.VAPID_ADMIN_EMAIL)
                }
            }

            # payload = {"head": "omg!", "body": "My first web push!"}

            data = json.dumps({
                "head": "omg!",
                "body": "NOT My first json web push!",
                "url": "https://nicksellen.co.uk"
            })

            print(
                'sending push!',
                subscription_info,
                data,
                dict(
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
                ),
            )

            webpush(
                subscription_info,
                data,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            )
