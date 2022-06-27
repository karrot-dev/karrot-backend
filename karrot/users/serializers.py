from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.serializers import SerializerMethodField
from versatileimagefield.serializers import VersatileImageFieldSerializer


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'username',
            'display_name',
        ]


class UserSerializer(serializers.ModelSerializer):
    photo_urls = VersatileImageFieldSerializer(sizes='user_profile', source='photo')

    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'username',
            'display_name',
            'photo_urls',
            'latitude',
            'longitude',
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    photo_urls = VersatileImageFieldSerializer(sizes='user_profile', source='photo')
    email = SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'username',
            'display_name',
            'email',
            'mobile_number',
            'address',
            'latitude',
            'longitude',
            'description',
            'photo_urls',
            'groups',
        ]

    def get_email(self, user):
        request = self.context.get('request', None)

        # can always see your own email address
        if request and request.user == user:
            return user.email

        # we only return email if we have a group context
        group = self.context.get('group', None)
        if not group:
            return None

        membership = group.groupmembership_set.get(user=user)
        return user.email if membership.is_email_visible else None
