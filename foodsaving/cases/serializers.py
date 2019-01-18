from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.utils.translation import ugettext as _

from foodsaving.cases import stats
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
        existing = []
        for option_id, data in validated_data.items():
            vote = votes.get(option_id, None)
            if vote is not None:
                if vote.score == data['score']:
                    existing.append(vote)
                    continue
                vote.delete()
            created.append(Vote.objects.create(**data))

        voting = self.context['voting']
        if len(votes) == 0:
            stats.voted(voting.case)
        elif len(created) > 0:
            stats.vote_changed(voting.case)

        return created + existing


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

    def validate_option(self, option):
        voting = self.context['voting']
        if option.voting != voting:
            raise serializers.ValidationError(_('Provided option is not part of this voting'))
        return option

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

    sum_score = serializers.SerializerMethodField()
    your_score = serializers.SerializerMethodField()

    def get_sum_score(self, option):
        if not option.voting.is_expired():
            return None
        return option.sum_score

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
            'participant_count',
        ]

    options = OptionSerializer(many=True, read_only=True)


class ConflictResolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = [
            'id',
            'created_at',
            'created_by',
            'status',
            'type',
            'topic',
            'votings',
            'group',
            'affected_user',
        ]
        read_only_fields = [
            'created_at',
            'created_by',
            'status',
            'type',
        ]
        extra_kwargs = {'created_by': {'default': serializers.CurrentUserDefault()}}

    votings = VotingSerializer(many=True, read_only=True)

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        if group.is_open:
            raise serializers.ValidationError('Cannot create conflict resolution in open group')
        return group

    def validate_affected_user(self, affected_user):
        if affected_user == self.context['request'].user:
            raise serializers.ValidationError('You cannot start a conflict resolution against yourself')
        return affected_user

    def validate_topic(self, topic):
        if len(topic) < 1:
            raise serializers.ValidationError(_('Topic cannot be empty'))
        return topic

    def validate(self, attrs):
        group = attrs['group']
        affected_user = attrs['affected_user']
        if not group.is_member(affected_user):
            raise serializers.ValidationError(_('Affected user is not part of that group'))
        if Case.objects.ongoing().filter(group=group, affected_user=affected_user).exists():
            raise serializers.ValidationError(
                _('A conflict resolution about that user in that group has already been started')
            )
        return attrs

    def save(self, **kwargs):
        return super().save(created_by=self.context['request'].user)
