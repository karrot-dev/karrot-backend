import pytz
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from foodsaving.groups.models import Group as GroupModel, GroupMembership
from django.conf import settings
from foodsaving.groups.signals import post_group_modify, post_group_create
from foodsaving.history.utils import get_changed_data


class TimezoneField(serializers.Field):
    def to_representation(self, obj):
        return str(obj)

    def to_internal_value(self, data):
        try:
            return pytz.timezone(str(data))
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValidationError(_('Unknown timezone'))


class GroupDetailSerializer(serializers.ModelSerializer):
    "use this also for creating and updating a group"

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'description',
            'public_description',
            'members',
            'address',
            'latitude',
            'longitude',
            'password',
            'timezone',
            'slack_webhook'
        ]
        extra_kwargs = {
            'name': {
                'min_length': 5
            },
            'members': {
                'read_only': True
            },
            'description': {
                'trim_whitespace': False,
                'max_length': settings.DESCRIPTION_MAX_LENGTH
            },
            'password': {
                'trim_whitespace': False,
                'max_length': 255
            }
        }

    timezone = TimezoneField()

    def update(self, group, validated_data):
        changed_data = get_changed_data(group, validated_data)
        group = super().update(group, validated_data)

        if changed_data:
            post_group_modify.send(
                sender=self.__class__,
                group=group,
                user=self.context['request'].user,
                payload=changed_data)
        return group

    def create(self, validated_data):
        user = self.context['request'].user
        group = GroupModel.objects.create(**validated_data)
        GroupMembership.objects.create(group=group, user=user)
        group.save()
        post_group_create.send(sender=self.__class__, group=group, user=user, payload=self.initial_data)
        return group


class GroupPreviewSerializer(serializers.ModelSerializer):
    """
    Public information for all visitors
    should be readonly
    """

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'public_description',
            'address',
            'latitude',
            'longitude',
            'members',
            'protected'
        ]

    protected = serializers.SerializerMethodField()

    def get_protected(self, group):
        return group.password != ''


class GroupJoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupModel
        fields = ['password']

    def validate(self, attrs):
        if self.instance.password != '' and self.instance.password != attrs.get('password'):
            raise ValidationError(_('Group password is wrong'))
        return attrs

    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.add_member(user)
        return instance


class GroupLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupModel
        fields = []

    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.remove_member(user)
        return instance


class TimezonesSerializer(serializers.Serializer):
    all_timezones = serializers.ListField(
        child=serializers.CharField(),
        read_only=True
    )
