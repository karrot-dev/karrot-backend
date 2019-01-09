from rest_framework import serializers

from foodsaving.cases.models import Case, Voting, Vote, Proposal


class ProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        fields = [
            'id',
            'type',
            'message',
            'affected_user',
            'result',
        ]

    result = serializers.SerializerMethodField()

    def get_result(self, proposal):
        if not proposal.voting.is_expired():
            return None
        return {
            'mean_score': 7.5,
            'accepted': True,
        }


class VotingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voting
        fields = [
            'status',
            'expires_at',
            'proposals',
        ]

    proposals = ProposalSerializer(many=True, read_only=True)


class CasesSerializer(serializers.ModelSerializer):
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
        ]
        read_only_fields = [
            'created_at',
            'created_by',
            'status',
            'type',
        ]
        extra_kwargs = {'created_by': {'default': serializers.CurrentUserDefault()}}

    votings = VotingSerializer(many=True, read_only=True)

    def save(self, **kwargs):
        return super().save(created_by=self.context['request'].user)


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = ['proposal', 'score']

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)
