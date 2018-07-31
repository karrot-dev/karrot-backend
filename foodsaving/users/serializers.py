from django.contrib.auth import get_user_model
from rest_framework import serializers
from versatileimagefield.serializers import VersatileImageFieldSerializer

from foodsaving.groups.serializers import GroupMembershipInfoSerializer


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'display_name',
        ]


class UserSerializer(serializers.ModelSerializer):
    photo_urls = VersatileImageFieldSerializer(sizes='user_profile', source='photo')

    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'display_name',
            'photo_urls',
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    photo_urls = VersatileImageFieldSerializer(sizes='user_profile', source='photo')
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            'id',
            'display_name',
            'email',
            'mobile_number',
            'address',
            'latitude',
            'longitude',
            'description',
            'photo_urls',
            'memberships',
        ]

    def get_memberships(self, user):
        return {m.group_id: GroupMembershipInfoSerializer(m).data for m in user.groupmembership_set.all()}
