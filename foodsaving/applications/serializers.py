from django.utils.translation import ugettext as _
from rest_framework import serializers

from foodsaving.applications.models import GroupApplication, GroupApplicationStatus
from foodsaving.users.serializers import UserSerializer


class GroupApplicationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupApplication
        fields = [
            'id',
            'created_at',
            'user',
            'group',
            'questions',
            'answers',
            'status',
            'decided_by',
            'decided_at',
        ]
        read_only_fields = [
            'user',
            'questions',
            'status',
        ]

    def validate(self, attrs):
        if GroupApplication.objects.filter(
                group=attrs.get('group'),
                user=self.context['request'].user,
                status=GroupApplicationStatus.PENDING.value,
        ).exists():
            raise serializers.ValidationError(_('Application is already pending'))
        return attrs

    def validate_group(self, group):
        if group.is_member(self.context['request'].user):
            raise serializers.ValidationError(_('You are already member of the group'))
        if group.is_open:
            raise serializers.ValidationError(_('You cannot apply to open groups'))
        return group

    def save(self, **kwargs):
        group = self.validated_data['group']
        return super().save(
            **kwargs,
            user=self.context['request'].user,
            questions=group.get_application_questions_or_default(),
        )
