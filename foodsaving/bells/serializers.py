from rest_framework import serializers

from foodsaving.bells.models import Bell


class BellSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bell
        fields = ['type', 'created_at', 'expires_at']
