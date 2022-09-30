from typing import List

import pytz
from django.conf import settings
from django.contrib.gis.geos import Point
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.fields import Field
from versatileimagefield.serializers import VersatileImageFieldSerializer

from karrot.groups.models import Group as GroupModel, GroupMembership, Agreement, UserAgreement, \
    GroupNotificationType, Trust
from karrot.history.models import History, HistoryTypus
from karrot.utils.misc import find_changed
from karrot.utils.validators import prevent_reserved_names
from . import roles
from karrot.utils.geoip import geoip_is_available, get_client_ip, ip_to_lat_lon
from .roles import GROUP_EDITOR


@extend_schema_field(OpenApiTypes.STR)
class TimezoneField(serializers.Field):
    def to_representation(self, obj):
        return str(obj)

    def to_internal_value(self, data):
        try:
            return pytz.timezone(str(data))
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValidationError(_('Unknown timezone'))


class GroupBaseSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.is_playground():
            if 'name' in ret:
                ret['name'] = _('Playground')
            if 'public_description' in ret:
                ret['public_description'] = render_to_string('playground_public_description.nopreview.jinja2')
        return ret


class GroupMembershipInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupMembership
        fields = (
            'created_at',
            'added_by',
            'roles',
            'active',
            'trusted_by',
            'trust',
        )
        read_only_fields = ['created_at', 'roles', 'added_by', 'trust']

    active = serializers.SerializerMethodField()
    trusted_by = serializers.SerializerMethodField()
    trust = serializers.SerializerMethodField()

    def get_active(self, membership):
        return membership.inactive_at is None

    def get_trusted_by(self, membership):
        # make it mean what the old trusted_by field meant: user ids that trusted them for editor role
        return [t.given_by_id for t in membership.trust_set.all() if t.role == GROUP_EDITOR]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_trust(self, membership):
        return [GroupMembershipTrustSerializer(t).data for t in membership.trust_set.all()]


class GroupMembershipTrustSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trust
        fields = (
            'given_by',
            'role',
            'created_at',
        )


class GroupHistorySerializer(GroupBaseSerializer):
    timezone = TimezoneField()

    class Meta:
        model = GroupModel
        exclude = ['photo']


class GroupDetailSerializer(GroupBaseSerializer):
    "use this also for creating and updating a group"
    memberships = serializers.SerializerMethodField()
    notification_types = serializers.SerializerMethodField()
    photo = VersatileImageFieldSerializer(sizes='group_logo', required=False, allow_null=True, write_only=True)
    photo_urls = VersatileImageFieldSerializer(sizes='group_logo', read_only=True, source='photo')
    timezone = TimezoneField()

    # setting constants
    member_inactive_after_days = serializers.SerializerMethodField()

    @staticmethod
    def get_member_inactive_after_days(_) -> int:
        return settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP

    issue_voting_duration_days = serializers.SerializerMethodField()

    @staticmethod
    def get_issue_voting_duration_days(_) -> int:
        return settings.VOTING_DURATION_DAYS

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'description',
            'welcome_message',
            'public_description',
            'application_questions',
            'application_questions_default',
            'members',
            'memberships',
            'roles',
            'address',
            'latitude',
            'longitude',
            'timezone',
            'active_agreement',
            'status',
            'theme',
            'features',
            'notification_types',
            'is_open',
            'trust_threshold_for_newcomer',
            'member_inactive_after_days',
            'issue_voting_duration_days',
            'photo',
            'photo_urls',
        ]
        extra_kwargs = {
            'name': {
                'min_length': 5,
                'validators': [prevent_reserved_names],
            },
            'description': {
                'trim_whitespace': False,
                'max_length': settings.DESCRIPTION_MAX_LENGTH
            },
            'welcome_message': {
                'trim_whitespace': False,
            },
        }
        read_only_fields = [
            'active',
            'members',
            'memberships',
            'roles',
            'notification_types',
            'is_open',
            'theme',
            'features',
        ]

    roles = serializers.SerializerMethodField()

    def validate_active_agreement(self, active_agreement):
        user = self.context['request'].user
        group = self.instance
        membership = GroupMembership.objects.filter(user=user, group=group).first()
        if roles.GROUP_AGREEMENT_MANAGER not in membership.roles:
            raise PermissionDenied(_('You cannot manage agreements'))
        if active_agreement and active_agreement.group != group:
            raise ValidationError(_('Agreement is not for this group'))
        return active_agreement

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_memberships(self, group):
        return {m.user_id: GroupMembershipInfoSerializer(m).data for m in group.groupmembership_set.all()}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_roles(self, group):
        # does not include 'editor', as it is a built-in role right now
        return {
            role.name: {
                'display_name': role.display_name,
                'description': role.description,
                'threshold': role.threshold,
            }
            for role in group.roles.all()
        }

    def get_notification_types(self, group) -> List[str]:
        user = self.context['request'].user
        membership = next(m for m in group.groupmembership_set.all() if m.user_id == user.id)
        return membership.notification_types

    def update(self, group, validated_data):
        if group.is_playground():
            # Prevent editing of public fields
            # Those fields get overridden with a translation message
            for field in ['name', 'public_description']:
                if field in validated_data:
                    del validated_data[field]

        if 'photo' in validated_data:
            group.delete_photo()

        changed_data = find_changed(group, validated_data)
        before_data = GroupHistorySerializer(group).data
        group = super().update(group, validated_data)
        after_data = GroupHistorySerializer(group).data

        if before_data != after_data:
            user = self.context['request'].user
            History.objects.create(
                typus=HistoryTypus.GROUP_MODIFY,
                group=group,
                users=[user],
                payload={k: self.initial_data.get(k)
                         for k in changed_data.keys()},
                before=before_data,
                after=after_data,
            )

        if 'photo' in validated_data:
            deleted = validated_data['photo'] is None
            History.objects.create(
                typus=HistoryTypus.GROUP_DELETE_PHOTO if deleted else HistoryTypus.GROUP_CHANGE_PHOTO,
                group=group,
                users=[self.context['request'].user],
            )
        return group

    def create(self, validated_data):
        user = self.context['request'].user
        group = GroupModel.objects.create(**validated_data)

        # create first member and make it receive application notifications
        membership = GroupMembership.objects.create(
            group=group, user=user, roles=[roles.GROUP_MEMBER, roles.GROUP_EDITOR]
        )
        membership.add_notification_types([GroupNotificationType.NEW_APPLICATION])
        membership.save()

        # create the initial types
        group.create_default_types()

        History.objects.create(
            typus=HistoryTypus.GROUP_CREATE,
            group=group,
            users=[user],
            payload=self.initial_data,
            after=GroupHistorySerializer(group).data
        )
        return group


class AgreementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agreement
        fields = [
            'id',
            'title',
            'content',
            'group',
            'agreed',
        ]
        extra_kwargs = {
            'agreed': {
                'read_only': True
            },
        }

    agreed = serializers.SerializerMethodField()

    def get_agreed(self, agreement) -> bool:
        return UserAgreement.objects.filter(user=self.context['request'].user, agreement=agreement).exists()

    def validate_group(self, group):
        membership = GroupMembership.objects.filter(user=self.context['request'].user, group=group).first()
        if not membership:
            raise PermissionDenied(_('You are not in this group'))
        if roles.GROUP_AGREEMENT_MANAGER not in membership.roles:
            raise PermissionDenied(_('You cannot manage agreements'))
        return group


class AgreementAgreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agreement
        fields = [
            'id',
            'title',
            'content',
            'group',
            'agreed',
        ]
        extra_kwargs = {
            'agreed': {
                'read_only': True
            },
        }

    agreed = serializers.SerializerMethodField()

    def get_agreed(self, agreement) -> bool:
        return UserAgreement.objects.filter(user=self.context['request'].user, agreement=agreement).exists()

    def update(self, instance, validated_data):
        user = self.context['request'].user
        if not UserAgreement.objects.filter(user=user, agreement=instance).exists():
            UserAgreement.objects.create(user=user, agreement=instance)
        return instance


class TrustActionSerializer(serializers.ModelSerializer):
    """Responsible for both creating and destroying trust"""
    class Meta:
        model = GroupMembership
        fields = ('role', )

    # default so it works with non-trust-for-role aware frontend
    role = serializers.CharField(default=GROUP_EDITOR)

    def validate_role(self, role_name):
        group = self.instance.group
        if role_name not in group.all_role_names:
            raise ValidationError(f'Invalid role "{role_name}" for group, available roles are {group.all_role_names}')
        if role_name != 'editor':
            role = group.roles.get(name=role_name)
            if role.role_required_for_trust and not group.is_member_with_role(self.context['request'].user,
                                                                              role.role_required_for_trust):
                raise ValidationError(
                    f'Trust for role "{role_name}" can only be given by users with "{role.role_required_for_trust}" role'
                )

        return role_name

    def update(self, membership, validated_data):
        request = self.context['request']
        user = request.user
        params = dict(
            membership=membership,
            given_by=user,
            role=validated_data['role'],
        )

        if request.method == 'POST':
            trust, created = Trust.objects.get_or_create(**params)
            if not created:
                raise ValidationError('You already gave trust to this user')

        elif request.method == 'DELETE':
            Trust.objects.get(**params).delete()

        return membership


@extend_schema_field(OpenApiTypes.INT)
class DistanceField(Field):
    """
    Returns distance of the object from users current location.
    - the object must have latitude/longitude fields
    - the users location is determined via geoip if available
    - the geoip lookup is cached in an lru_cache
    - the return unit is km rounded to the nearest km

    It may return None under various conditions:
    - the GeoIP2 libary was not initialized (missing the files)
    - there is no request context
    - we cannot determine the IP address of the client
    - the IP address cannot be found in the database
    """
    def __init__(self, **kwargs):
        kwargs['source'] = '*'
        kwargs['read_only'] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not geoip_is_available():
            return None

        if not (hasattr(value, 'latitude') and hasattr(value, 'longitude')):
            raise Exception('Must have latitude and longitude fields to use DistanceField')

        if not value.latitude or not value.longitude:
            return None

        request = self.context.get('request', None)
        if not request:
            return None

        client_ip = get_client_ip(request)
        if not client_ip:
            return None

        current_lat_lon = ip_to_lat_lon(client_ip)

        if not current_lat_lon:
            return None

        # use WGS84
        # https://docs.djangoproject.com/en/3.1/ref/contrib/gis/model-api/#django.contrib.gis.db.models.BaseSpatialField.srid
        srid = 4326
        current_point = Point(current_lat_lon[1], current_lat_lon[0], srid=srid)
        point = Point(value.longitude, value.latitude, srid=srid)

        # I don't think this does any fancy curvature calculation, probably enough though :)
        # not sure what unit or the * 100 is? I took it from https://gis.stackexchange.com/a/21871
        # it seems to be km (I calculated distance using another tool to compare)
        return round(current_point.distance(point) * 100)


class GroupPreviewSerializer(GroupBaseSerializer):
    """
    Public information for all visitors
    should be readonly
    """
    application_questions = serializers.SerializerMethodField()
    photo_urls = VersatileImageFieldSerializer(sizes='group_logo', read_only=True, source='photo')
    distance = DistanceField()
    member_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'public_description',
            'application_questions',
            'address',
            'latitude',
            'longitude',
            'member_count',
            'is_member',
            'status',
            'theme',
            'is_open',
            'photo_urls',
            'distance',
        ]

    def get_application_questions(self, group) -> str:
        return group.get_application_questions_or_default()

    def get_member_count(self, group) -> int:
        if hasattr(group, 'member_count'):
            return group.member_count

        return group.members.count()

    def get_is_member(self, group) -> bool:
        user = self.context['request'].user if 'request' in self.context else None
        if not user or user.is_anonymous:
            return False

        if hasattr(group, 'is_user_member'):
            return group.is_user_member

        return user in group.members.all()


class GroupJoinSerializer(GroupBaseSerializer):
    class Meta:
        model = GroupModel
        fields = []

    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.add_member(user)
        return instance


class GroupLeaveSerializer(GroupBaseSerializer):
    class Meta:
        model = GroupModel
        fields = []

    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.remove_member(user)
        return instance


class TimezonesSerializer(serializers.Serializer):
    all_timezones = serializers.ListField(child=serializers.CharField(), read_only=True)


class GroupMembershipAddNotificationTypeSerializer(serializers.Serializer):
    notification_type = serializers.ChoiceField(
        choices=[(choice, choice) for choice in (
            GroupNotificationType.WEEKLY_SUMMARY,
            GroupNotificationType.DAILY_ACTIVITY_NOTIFICATION,
            GroupNotificationType.NEW_APPLICATION,
            GroupNotificationType.NEW_OFFER,
            GroupNotificationType.CONFLICT_RESOLUTION,
        )],
        required=True,
        write_only=True
    )

    def update(self, instance, validated_data):
        notification_type = validated_data['notification_type']
        instance.add_notification_types([notification_type])
        instance.save()
        return instance


class GroupMembershipRemoveNotificationTypeSerializer(serializers.Serializer):
    notification_type = serializers.CharField(required=True, write_only=True)

    def update(self, instance, validated_data):
        notification_type = validated_data['notification_type']
        instance.remove_notification_types([notification_type])
        instance.save()
        return instance
