from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ModelSerializer

from karrot.agreements.models import Agreement


class AgreementSerializer(ModelSerializer):
    class Meta:
        model = Agreement
        fields = [
            'id',
            'title',
            'summary',
            'content',
            'active_from',
            'active_to',
            'review_at',
            'group',
            'created_by',
            'last_changed_by',
        ]
        read_only_fields = [
            'last_changed_by',
        ]

    def validate_group(self, group):
        if self.instance is not None:
            raise PermissionDenied('You cannot change the group')
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied('You are not a member of this group.')
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied('You need to be a group editor')
        return group

    def save(self, **kwargs):
        current_user = self.context['request'].user
        extra_kwargs = dict(last_changed_by=current_user)
        if self.instance is None:
            extra_kwargs.update(created_by=current_user)
        return super().save(**kwargs, **extra_kwargs)
