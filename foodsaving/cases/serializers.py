from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.utils.translation import ugettext as _

from foodsaving.cases.models import Case, Voting, Vote, Option


class VoteListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        mapping = {vote['option'].id: vote for vote in attrs}
        voting = self.context['voting']
        if not all((option.id in mapping) for option in voting.options.all()):
            raise serializers.ValidationError(_('You need to provide a score for all options'))

        return mapping

    def save(self, **kwargs):
        return self.update(self.instance, self.validated_data)

    def update(self, instance, validated_data):
        votes = {vote.option_id: vote for vote in instance}

        created = []
        for option_id, data in validated_data.items():
            vote = votes.get(option_id, None)
            if vote is not None:
                vote.delete()
            created.append(Vote.objects.create(**data))

        return created


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        list_serializer_class = VoteListSerializer
        fields = [
            'option',
            'score',
            'user',
        ]
        extra_kwargs = {
            'user': {
                'write_only': True,
                'default': serializers.CurrentUserDefault(),
            },
        }

    def valiate_option(self, option):
        voting = self.context['voting']
        if option.voting != voting:
            raise serializers.ValidationError(_('Provided option is not part of this voting'))

    def validate_score(self, score):
        if not -2 <= score <= 2:
            raise serializers.ValidationError(_('Provided score is outside of allowed range'))
        return score


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = [
            'id',
            'type',
            'message',
            'affected_user',
            'sum_score',
            'your_score',
        ]

    your_score = serializers.SerializerMethodField()

    def get_your_score(self, option):
        try:
            vote = option.votes.get(user=self.context['request'].user)
        except Vote.DoesNotExist:
            return None
        return vote.score


class VotingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voting
        fields = [
            'id',
            'expires_at',
            'options',
            'accepted_option',
            'participants',
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
