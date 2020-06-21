from rest_framework import serializers

from karrot.notifications.models import Notification, NotificationMeta


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "created_at",
            "expires_at",
            "clicked",
            "context",
        ]


class NotificationMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationMeta
        fields = ["marked_at"]
