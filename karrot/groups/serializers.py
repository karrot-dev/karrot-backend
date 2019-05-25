import pytz
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from versatileimagefield.serializers import VersatileImageFieldSerializer

from karrot.groups.models import Group as GroupModel, GroupMembership, Agreement, UserAgreement, \
    GroupNotificationType
from karrot.history.models import History, HistoryTypus
from karrot.utils.misc import find_changed
from karrot.utils.validators import prevent_reserved_names
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
            'added_by',
            'roles',
            'active',
            'trusted_by',
        )
        read_only_fields = ['created_at', 'roles', 'added_by']

    active = serializers.SerializerMethodField()

    def get_active(self, membership):
        return membership.inactive_at is None


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
    member_inactive_after_days = serializers.ReadOnlyField(default=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP)
    issue_voting_duration_days = serializers.ReadOnlyField(default=settings.VOTING_DURATION_DAYS)
    active_editors_required_for_conflict_resolution = serializers.ReadOnlyField(
        default=settings.CONFLICT_RESOLUTION_ACTIVE_EDITORS_REQUIRED_FOR_CREATION
    )

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
            'address',
            'latitude',
            'longitude',
            'timezone',
            'active_agreement',
            'status',
            'theme',
            'notification_types',
            'is_open',
            'trust_threshold_for_newcomer',
            'member_inactive_after_days',
            'issue_voting_duration_days',
            'active_editors_count',
            'active_editors_required_for_conflict_resolution',
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
            'notification_types',
            'is_open',
            'theme',
        ]

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
        membership = GroupMembership.objects.create(group=group, user=user, roles=[roles.GROUP_EDITOR])
        membership.add_notification_types([GroupNotificationType.NEW_APPLICATION])
        membership.save()

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
    photo_urls = VersatileImageFieldSerializer(sizes='group_logo', read_only=True, source='photo')

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
            'theme',
            'is_open',
            'photo_urls',
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


class GroupMembershipAddNotificationTypeSerializer(serializers.Serializer):
    notification_type = serializers.ChoiceField(
        choices=[(choice, choice) for choice in (
            GroupNotificationType.WEEKLY_SUMMARY,
            GroupNotificationType.DAILY_PICKUP_NOTIFICATION,
            GroupNotificationType.NEW_APPLICATION,
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
