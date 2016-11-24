from django.contrib.auth import get_user_model
from rest_framework import serializers
from versatileimagefield.serializers import VersatileImageFieldSerializer
from yunity.users.models import ProfilePicture as ProfilePictureModel


class ProfilePictureSerializer(serializers.ModelSerializer):
    image = VersatileImageFieldSerializer(
        # defined in config/versatileimagefield.py
        sizes='profile_image'
    )

    class Meta:
        model = ProfilePictureModel
        fields = ['image', ]


class UserSerializer(serializers.ModelSerializer):
    profile_picture = ProfilePictureSerializer(allow_null=True, required=False)

    class Meta:
        model = get_user_model()
        fields = ['id', 'display_name', 'first_name', 'last_name', 'email', 'password',
                  'address', 'latitude', 'longitude', 'profile_picture']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        picture_data = validated_data.pop('profile_picture', None)
        user = self.Meta.model.objects.create_user(**validated_data)
        if picture_data:
            ProfilePictureModel.objects.create(user=user, **picture_data)
        return user
