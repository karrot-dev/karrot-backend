from rest_framework import serializers

from foodsaving.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'created_at', 'expires_at', 'context']
