from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from karrot.subscriptions.models import PushSubscription


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ['id', 'token', 'platform']


class CreatePushSubscriptionSerializer(PushSubscriptionSerializer):
    class Meta(PushSubscriptionSerializer.Meta):
        fields = PushSubscriptionSerializer.Meta.fields + ['user']
        extra_kwargs = {'user': {'default': serializers.CurrentUserDefault()}}
        validators = [
            UniqueTogetherValidator(
                queryset=PushSubscription.objects.all(),
                fields=PushSubscription._meta.unique_together[0]  # only supports first tuple
            )
        ]

    def validate(self, attrs):
        attrs['user'] = self.context['request'].user
        return attrs
