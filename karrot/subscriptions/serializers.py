from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from karrot.subscriptions.models import PushSubscription, WebPushSubscription


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


# TODO(PR): do I need this?
class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = ['id', 'endpoint', 'keys', 'browser', 'user_agent']


class CreateWebPushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = ['endpoint', 'keys', 'mobile', 'browser', 'version', 'os']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    # def validate(self, attrs):
    #     attrs['user'] = self.context['request'].user
    #     return attrs
