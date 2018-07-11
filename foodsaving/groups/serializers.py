import pytz
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.conversations.models import Conversation, ConversationMessage
from foodsaving.groups.models import Group as GroupModel, GroupMembership, Agreement, UserAgreement, \
    GroupNotificationType, GroupApplication
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
        fields = ('created_at', 'roles', 'active',)
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
    timezone = TimezoneField()

    class Meta:
        model = GroupModel
        fields = [
            'id',
            'name',
            'description',
            'public_description',
            'application_questions',
            'members',
            'memberships',
            'address',
            'latitude',
            'longitude',
            'password',
            'timezone',
            'active_agreement',
            'status',
            'notification_types',
        ]
        extra_kwargs = {
            'name': {
                'min_length': 5
            },
            'description': {
                'trim_whitespace': False,
                'max_length': settings.DESCRIPTION_MAX_LENGTH
            },
            'password': {
                'trim_whitespace': False,
                'max_length': 255
            },
        }
        read_only_fields = ['active', 'members', 'memberships', 'notification_types']

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

    def update(self, group, validated_data):
        if group.is_playground():
            # Prevent editing of public fields
            # Password shouldn't get changed and the others get overridden with a translation message
            for field in ['name', 'password', 'public_description']:
                if field in validated_data:
                    del validated_data[field]

        changed_data = get_changed_data(group, validated_data)
        group = super().update(group, validated_data)

        if changed_data:
            user = self.context['request'].user
            History.objects.create(
                typus=HistoryTypus.GROUP_MODIFY,
                group=group,
                users=[user, ],
                payload=changed_data
            )
        return group

    def create(self, validated_data):
        user = self.context['request'].user
        group = GroupModel.objects.create(**validated_data)
        GroupMembership.objects.create(group=group, user=user)
        History.objects.create(
            typus=HistoryTypus.GROUP_CREATE,
            group=group,
            users=[user, ],
            payload=self.initial_data
        )
        return group


class GroupApplicationSerializer(serializers.ModelSerializer):
    conversation = serializers.SerializerMethodField()
    message = serializers.CharField(
        write_only=True,
        required=True,
    )

    class Meta:
        model = GroupApplication
        fields = [
            'id',
            'user',
            'group',
            'conversation',
            'message',
        ]
        read_only_fields = [
            'user',
        ]
        extra_kwargs = {
            'user': {'default': serializers.CurrentUserDefault()},
        }
        validators = [
            UniqueTogetherValidator(
                queryset=GroupApplication.objects.all(),
                fields=GroupApplication._meta.unique_together[0],
                message='You already applied for the group',
            )
        ]

    def get_conversation(self, application):
        return Conversation.objects.get_for_target(application).id

    def validate_user(self, user):
        if not user.mail_verified:
            raise PermissionDenied(_('You need to verify your email address before you can apply for a group'))
        return user

    def validate_group(self, group):
        if group.is_member(self.context['request'].user):
            raise serializers.ValidationError('You are already member of the group')
        return group

    def validate(self, attrs):
        attrs['user'] = self.context['request'].user
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        message = validated_data.pop('message')
        application = GroupApplication.objects.create(**validated_data)
        conversation = Conversation.objects.get_for_target(application)
        ConversationMessage.objects.create(
            author=self.context['request'].user,
            conversation=conversation,
            content=message,
        )
        return application


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
            'protected',
            'status',
        ]

    protected = serializers.SerializerMethodField()

    def get_protected(self, group):
        return group.password != ''


class GroupJoinSerializer(GroupBaseSerializer):
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


class GroupLeaveSerializer(GroupBaseSerializer):
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


class EmptySerializer(serializers.Serializer):
    pass


class GroupMembershipAddRoleSerializer(serializers.Serializer):
    role_name = serializers.ChoiceField(
        choices=(roles.GROUP_MEMBERSHIP_MANAGER, roles.GROUP_AGREEMENT_MANAGER,),
        required=True,
        write_only=True
    )

    def update(self, instance, validated_data):
        role = validated_data['role_name']
        instance.add_roles([role])
        instance.save()
        return instance


class GroupMembershipRemoveRoleSerializer(serializers.Serializer):
    role_name = serializers.CharField(
        required=True,
        write_only=True
    )

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
    notification_type = serializers.CharField(
        required=True,
        write_only=True
    )

    def update(self, instance, validated_data):
        notification_type = validated_data['notification_type']
        instance.remove_notification_types([notification_type])
        instance.save()
        return instance
