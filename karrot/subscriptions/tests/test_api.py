import factory
from django.db.models.signals import post_save
from factory.django import mute_signals
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.subscriptions.factories import WebPushSubscriptionFactory
from karrot.subscriptions.models import WebPushSubscription
from karrot.users.factories import UserFactory


class TestSubscriptionsAPI(APITestCase):
    @mute_signals(post_save)
    def test_create_push_subscription(self):
        user = UserFactory()
        self.client.force_login(user=user)

        data: dict = factory.build(dict, FACTORY_CLASS=WebPushSubscriptionFactory)
        data.pop('user')
        response = self.client.post('/api/subscriptions/web-push/subscribe/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_can_delete_subscriptions(self):
        user = UserFactory()
        with mute_signals(post_save):
            subscription = WebPushSubscriptionFactory(user=user)
        self.client.force_login(user=user)
        data = {'endpoint': subscription.endpoint, 'keys': subscription.keys}
        response = self.client.post('/api/subscriptions/web-push/unsubscribe/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(WebPushSubscription.objects.filter(pk=subscription.id).count(), 0)
