from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from enum import Enum

from karrot.base.base_models import BaseModel


class ChannelSubscriptionQuerySet(models.QuerySet):
    def old(self):
        return self.filter(lastseen_at__lt=timezone.now() - relativedelta(minutes=30))

    def recent(self):
        return self.filter(lastseen_at__gt=timezone.now() - relativedelta(seconds=20))


class ChannelSubscription(BaseModel):
    """A subscription to receive messages over a django channel."""
    objects = ChannelSubscriptionQuerySet.as_manager()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reply_channel = models.TextField()  # django channels channel
    lastseen_at = models.DateTimeField(default=timezone.now, null=True)
    away_at = models.DateTimeField(null=True)
    client_ip = models.GenericIPAddressField(null=True)


class PushSubscriptionPlatform(Enum):
    # these are both fcm
    ANDROID = 'android'
    WEB = 'web'


class PushSubscription(BaseModel):
    """A subscription to receive messages over an FCM push channel."""
    class Meta:
        unique_together = ('user', 'token')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.TextField()  # FCM device registration token
    platform = models.CharField(
        default=PushSubscriptionPlatform.ANDROID.value,
        choices=[(platform.value, platform.value) for platform in PushSubscriptionPlatform],
        max_length=100,
    )


class WebPushSubscription(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # subscription info
    endpoint = models.URLField(max_length=500)
    keys = models.JSONField()

    # extra info
    mobile = models.BooleanField()
    browser = models.CharField()
    version = models.CharField()
    os = models.CharField()
