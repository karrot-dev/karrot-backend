from django.contrib.auth import get_user_model
from rest_framework import serializers
from versatileimagefield.serializers import VersatileImageFieldSerializer
from django.utils import timezone
from django.conf import settings

class UserSerializer(serializers.ModelSerializer):

    photo_urls = VersatileImageFieldSerializer(
        sizes='user_profile',
        source='photo'
    )
    my_trust = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ['id', 'display_name', 'email', 'address', 'latitude', 'longitude', 'description', 'photo_urls', 'my_trust']


    def get_my_trust(self, user):
        auth_user = self.context['request'].user
        if not auth_user:
            return None

        trust = user.get_trust_by(auth_user)
        if not trust:
            return None

        # TODO: use a serialzer for that 
        expires = trust.created_at+timezone.timedelta(days=settings.TRUST_EXPIRE_TIME_DAYS)
        return {
            "created_at":trust.created_at,
            "expires": expires,
            "level": trust.level
        }
    