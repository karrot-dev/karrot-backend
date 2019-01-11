from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.utils.translation import ugettext as _

from foodsaving.cases.models import Case, Voting, Vote, Option


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = [
            'id',
            'type',
            'message',
            'affected_user',
            'mean_score',
        ]


class VotingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voting
        fields = [
            'expires_at',
            'options',
            'accepted_option',
        ]

    options = OptionSerializer(many=True, read_only=True)


class CasesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = [
            'id',
            'created_at',
            'created_by',
            'is_decided',
            'type',
            'topic',
            'votings',
            'group',
            'affected_user',
        ]
        read_only_fields = [
            'created_at',
            'created_by',
            'is_decided',
            'type',
        ]
        extra_kwargs = {'created_by': {'default': serializers.CurrentUserDefault()}}

    votings = VotingSerializer(many=True, read_only=True)

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        return group

    def validate(self, attrs):
        group = attrs['group']
        affected_user = attrs['affected_user']
        if not group.is_member(affected_user):
            raise serializers.ValidationError(_('Affected user is not part of that group'))
        if Case.objects.filter(group=group, affected_user=affected_user, is_decided=False).exists():
            raise serializers.ValidationError(_('A case about that user in that group has already been started'))
        return attrs

    def save(self, **kwargs):
        return super().save(created_by=self.context['request'].user)


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = [
            'option',
            'score',
        ]

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)
