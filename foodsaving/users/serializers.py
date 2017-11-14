from django.contrib.auth import get_user_model
from rest_framework import serializers
from versatileimagefield.serializers import VersatileImageFieldSerializer


class UserSerializer(serializers.ModelSerializer):

    photo = VersatileImageFieldSerializer(
        sizes='user_profile'
    )

    class Meta:
        model = get_user_model()
        fields = ['id', 'display_name', 'email', 'address', 'latitude', 'longitude', 'description', 'photo']
