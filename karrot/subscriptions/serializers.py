from rest_framework import serializers

from karrot.subscriptions.models import WebPushSubscription


class WebPushSubscribeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = ["endpoint", "keys", "mobile", "browser", "version", "os"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class WebPushUnsubscribeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = ["endpoint", "keys"]
