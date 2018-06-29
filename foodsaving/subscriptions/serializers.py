from rest_framework import serializers
from rest_framework.fields import CurrentUserDefault
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.subscriptions.models import PushSubscription
from foodsaving.users.serializers import UserSerializer


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = [
            'id',
            'token',
            'platform'
        ]


class CreatePushSubscriptionSerializer(PushSubscriptionSerializer):
    class Meta(PushSubscriptionSerializer.Meta):
        fields = PushSubscriptionSerializer.Meta.fields + [
            'user'
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=PushSubscription.objects.all(),
                fields=PushSubscription._meta.unique_together[0]  # only supports first tuple
            )
        ]

    # user field is only here so make the UniqueTogetherValidator work
    # https://stackoverflow.com/a/27239870
    # https://github.com/encode/django-rest-framework/issues/2164#issuecomment-65196943
    user = UserSerializer(
        read_only=True,
        default=CurrentUserDefault()
    )

    def validate(self, attrs):
        attrs['user'] = self.context['request'].user
        return attrs
