from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from enum import Enum

from foodsaving.base.base_models import BaseModel
from foodsaving.conversations.models import Conversation


class CaseStatus(Enum):
    ONGOING = 'ongoing'
    DECIDED = 'decided'


class CaseTypes(Enum):
    CONFLICT_RESOLUTION = 'conflict_resolution'


class Case(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='cases')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cases_opened')
    status = models.TextField(
        default=CaseStatus.ONGOING.value,
        choices=[(status.value, status.value) for status in CaseStatus],
    )
    type = models.TextField(
        default=CaseTypes.CONFLICT_RESOLUTION.value,
        choices=[(status.value, status.value) for status in CaseTypes],
    )
    topic = models.TextField()
    affected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE, related_name='affected_by_case'
    )

    def save(self, **kwargs):
        super().save(**kwargs)

        if self.votings.count() == 0:
            voting = self.votings.create()
            voting.proposals.create(type=ProposalTypes.FURTHER_DISCUSSION.value)
            voting.proposals.create(type=ProposalTypes.REMOVE_USER.value, affected_user=self.affected_user)
            voting.proposals.create(type=ProposalTypes.CUSTOM.value, message='Offline mediation')


class VotingStatus(Enum):
    ONGOING = 'ongoing'
    DECIDED = 'decided'


def voting_expiration_time():
    return timezone.now() + relativedelta(days=settings.CASE_VOTING_DURATION_DAYS)


class Voting(BaseModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='votings')
    status = models.TextField(
        default=VotingStatus.ONGOING.value,
        choices=[(status.value, status.value) for status in VotingStatus],
    )
    expires_at = models.DateTimeField(default=voting_expiration_time)

    def decide(self):
        self.status = VotingStatus.DECIDED.value
        self.save()

    def continue_discussion(self):
        new_voting = self.case.votings.create()
        for proposal in self.proposals.all():
            new_voting.proposals.create(
                type=proposal.type,
                affected_user=proposal.affected_user,
                message=proposal.message,
            )

    def is_expired(self):
        return self.expires_at < timezone.now()


class ProposalTypes(Enum):
    CUSTOM = 'custom'
    FURTHER_DISCUSSION = 'further_discussion'
    REMOVE_USER = 'remove_user'


class Proposal(BaseModel):
    voting = models.ForeignKey(Voting, on_delete=models.CASCADE, related_name='proposals')
    type = models.TextField(
        default=ProposalTypes.CUSTOM.value,
        choices=[(status.value, status.value) for status in ProposalTypes],
    )
    affected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE, related_name='affected_by_proposals'
    )
    message = models.TextField(null=True)


class Vote(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes_given')
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='votes')
    score = models.IntegerField()
