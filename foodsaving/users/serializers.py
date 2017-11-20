from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'display_name', 'email', 'address', 'latitude', 'longitude', 'description']


class VerifyMailSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=40, min_length=40)

    def validate_key(self, key):
        user = self.instance
        if user.key_expires_at < timezone.now():
            raise serializers.ValidationError(_('Key has expired'))
        if key != user.activation_key:
            raise serializers.ValidationError(_('Key is invalid'))
        return key

    def update(self, user, validated_data):
        user.verify_mail()
        return user
