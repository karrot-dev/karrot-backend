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
            'active_until',
            'review_at',
            'group',
        ]

    def validate_group(self, group):
        if self.instance is not None:
            raise PermissionDenied('You cannot change the group')
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied('You are not a member of this group.')
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied('You need to be a group editor')
        return group
