from rest_framework import serializers
from rest_framework.fields import SerializerMethodField, CurrentUserDefault
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.subscriptions.models import PushSubscription, PushSubscriptionPlatform
from foodsaving.users.serializers import UserIdSerializer


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = [
            'id',
            'user',
            'token',
            'platform'
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=PushSubscription.objects.all(),
                fields=('user', 'token')
            )
        ]

    user = UserIdSerializer(
        read_only=True,
        default=CurrentUserDefault()
    )

    platform = SerializerMethodField()

    def get_platform(self, obj):
        return PushSubscriptionPlatform.name(obj.platform).lower()
