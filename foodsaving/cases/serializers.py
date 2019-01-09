from rest_framework import serializers

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
