import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        # TODO use sparkpost subaccounts to receive correct emailevents

        hostname = 'https://3ac89d14.ngrok.io'

        s = requests.Session()
        s.headers.update({'Authorization': settings.ANYMAIL['SPARKPOST_API_KEY']})

        response = s.get('https://api.sparkpost.com/api/v1/webhooks')
        print(response.status_code, response.text)
        webhooks = response.json()
        for w in webhooks['results']:
            w_id = w['id']
            print('deleting webhook', w_id)
            response = s.delete('https://api.sparkpost.com/api/v1/webhooks/' + w_id)
            print(response.status_code, response.text)
        response = s.post(
            'https://api.sparkpost.com/api/v1/webhooks',
            json={
                "name": "local karrot webhook",
                "target": hostname + "/api/webhooks/email_event/",
                "auth_type": "basic",
                "auth_credentials": {"username": "xxx", "password": settings.SPARKPOST_WEBHOOK_KEY},
                "events": ["bounce", "injection", "spam_complaint", "out_of_band"],
            }
        )
        print(response.status_code, response.text)

        response = s.get('https://api.sparkpost.com/api/v1/relay-webhooks')
        relay_webhooks = response.json()
        for w in relay_webhooks['results']:
            w_id = w['id']
            print('deleting relay webhook', w_id)
            response = s.delete('https://api.sparkpost.com/api/v1/relay-webhooks/' + w_id)
            print(response.status_code, response.text)
        response = s.post(
            'https://api.sparkpost.com/api/v1/relay-webhooks',
            json={
                "name": "local karrot relay",
                "target": hostname + "/api/webhooks/incoming_email/",
                "auth_token": settings.SPARKPOST_INCOMING_KEY,
                "match": {"domain": "replies.karrot.world"}
            }
        )
        print(response.status_code, response.text)
