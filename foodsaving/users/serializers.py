from django.contrib.auth import get_user_model
from rest_framework import serializers
from versatileimagefield.serializers import VersatileImageFieldSerializer
from foodsaving.users.models import Trust


class UserSerializer(serializers.ModelSerializer):

    photo_urls = VersatileImageFieldSerializer(
        sizes='user_profile',
        source='photo'
    )
    my_trust = serializers.SerializerMethodField()

    def get_my_trust(self, user):

        request_user = self.context['request'].user
        if not request_user:
            return None

        trust = user.trusts.valid().filter(given_by=request_user).first()

        if not trust:
            return None

        return TrustSerializer(trust).data

    class Meta:
        model = get_user_model()
        fields = ['id', 'display_name', 'email', 'mobile_number', 'address',
                  'latitude', 'longitude', 'description', 'photo_urls', 'my_trust']


class TrustSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trust
        fields = ['valid_from', 'valid_until']
