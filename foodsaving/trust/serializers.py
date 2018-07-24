from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.trust.models import Trust


class TrustSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trust
        fields = [
            'id',
            'user',
            'group',
            'given_by',
        ]
        read_only_fields = ['given_by']
        extra_kwargs = {'given_by': {'default': serializers.CurrentUserDefault()}}
        validators = [
            UniqueTogetherValidator(
                queryset=Trust.objects.all(),
                fields=Trust._meta.unique_together[0]
            )
        ]

    def validate(self, attrs):
        group = attrs.get('group')
        user = attrs.get('user')
        if not group.is_member(user):
            raise serializers.ValidationError(_('User is not member of group'))
        return attrs

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise serializers.ValidationError(_('You need to be a member of the group'))
        if not group.is_editor(self.context['request'].user):
            raise serializers.ValidationError(_('You need to be a group editor'))
        return group

    def save(self, **kwargs):
        return super().save(
            **kwargs,
            given_by=self.context['request'].user,
        )
