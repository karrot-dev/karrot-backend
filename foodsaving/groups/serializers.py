import pytz
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied

from foodsaving.groups.models import Group as GroupModel, GroupMembership, Agreement, UserAgreement, \
    GroupNotificationType
from foodsaving.groups.roles import GROUP_EDITOR
from foodsaving.history.models import History, HistoryTypus
from foodsaving.history.utils import get_changed_data
from . import roles


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
            'roles',
            'active',
            'trusted_by',
        )
        extra_kwargs = {
            'created_at': {
                'read_only': True
            },
            'roles': {
                'read_only': True
            },
        }

    active = serializers.SerializerMethodField()

    def get_active(self, membership):
        return membership.inactive_at is None


class GroupDetailSerializer(GroupBaseSerializer):
    "use this also for creating and updating a group"
    memberships = serializers.SerializerMethodField()
    notification_types = serializers.SerializerMethodField()
    application_questions_default = serializers.SerializerMethodField()
    trust_threshold_for_newcomer = serializers.SerializerMethodField()

    timezone = TimezoneField()

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'description',
            'public_description',
            'application_questions',
            'application_questions_default',
            'members',
            'memberships',
            'address',
            'latitude',
            'longitude',
            'timezone',
            'active_agreement',
            'status',
            'notification_types',
            'is_open',
            'trust_threshold_for_newcomer',
        ]
        extra_kwargs = {
            'name': {
                'min_length': 5
            },
            'description': {
                'trim_whitespace': False,
                'max_length': settings.DESCRIPTION_MAX_LENGTH
            },
        }
        read_only_fields = ['active', 'members', 'memberships', 'notification_types', 'is_open']

    def validate_active_agreement(self, active_agreement):
        user = self.context['request'].user
        group = self.instance
        membership = GroupMembership.objects.filter(user=user, group=group).first()
        if roles.GROUP_AGREEMENT_MANAGER not in membership.roles:
            raise PermissionDenied(_('You cannot manage agreements'))
        if active_agreement and active_agreement.group != group:
            raise ValidationError(_('Agreement is not for this group'))
        return active_agreement

    def get_memberships(self, group):
        return {m.user_id: GroupMembershipInfoSerializer(m).data for m in group.groupmembership_set.all()}

    def get_notification_types(self, group):
        if 'request' not in self.context:
            return []
        user = self.context['request'].user
        membership = group.groupmembership_set.get(user=user)
        return membership.notification_types

    def get_application_questions_default(self, group):
        return group.get_application_questions_default()

    def get_trust_threshold_for_newcomer(self, group):
        return group.get_trust_threshold_for_newcomer()

    def update(self, group, validated_data):
        if group.is_playground():
            # Prevent editing of public fields
            # Password shouldn't get changed and the others get overridden with a translation message
            for field in ['name', 'public_description']:
                if field in validated_data:
                    del validated_data[field]

        changed_data = get_changed_data(group, validated_data)
        group = super().update(group, validated_data)

        if changed_data:
            user = self.context['request'].user
            History.objects.create(
                typus=HistoryTypus.GROUP_MODIFY, group=group, users=[
                    user,
                ], payload=changed_data
            )
        return group

    def create(self, validated_data):
        user = self.context['request'].user
        group = GroupModel.objects.create(**validated_data)
        GroupMembership.objects.create(group=group, user=user, roles=[roles.GROUP_EDITOR])
        History.objects.create(
            typus=HistoryTypus.GROUP_CREATE, group=group, users=[
                user,
            ], payload=self.initial_data
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

    def get_agreed(self, agreement):
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

    def get_agreed(self, agreement):
        return UserAgreement.objects.filter(user=self.context['request'].user, agreement=agreement).exists()

    def update(self, instance, validated_data):
        user = self.context['request'].user
        if not UserAgreement.objects.filter(user=user, agreement=instance).exists():
            UserAgreement.objects.create(user=user, agreement=instance)
        return instance


class GroupPreviewSerializer(GroupBaseSerializer):
    """
    Public information for all visitors
    should be readonly
    """
    application_questions = serializers.SerializerMethodField()

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
            'members',
            'status',
            'is_open',
        ]

    def get_application_questions(self, group):
        return group.get_application_questions_or_default()


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


class EmptySerializer(serializers.Serializer):
    pass


class GroupMembershipAddRoleSerializer(serializers.Serializer):
    role_name = serializers.ChoiceField(
        choices=(
            roles.GROUP_MEMBERSHIP_MANAGER,
            roles.GROUP_AGREEMENT_MANAGER,
        ), required=True, write_only=True
    )

    def validate_role_name(self, role_name):
        if role_name == GROUP_EDITOR:
            raise serializers.ValidationError('You cannot change the editor role')
        return role_name

    def update(self, instance, validated_data):
        role = validated_data['role_name']
        instance.add_roles([role])
        instance.save()
        return instance


class GroupMembershipRemoveRoleSerializer(serializers.Serializer):
    role_name = serializers.CharField(required=True, write_only=True)

    def validate_role_name(self, role_name):
        if role_name == GROUP_EDITOR:
            raise serializers.ValidationError('You cannot change the editor role')
        return role_name

    def update(self, instance, validated_data):
        role = validated_data['role_name']
        instance.remove_roles([role])
        instance.save()
        return instance


class GroupMembershipAddNotificationTypeSerializer(serializers.Serializer):
    notification_type = serializers.ChoiceField(
        choices=[(choice, choice) for choice in (
            GroupNotificationType.WEEKLY_SUMMARY,
            GroupNotificationType.DAILY_PICKUP_NOTIFICATION,
            GroupNotificationType.NEW_APPLICATION,
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
