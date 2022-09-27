from django.db import models

from karrot.base.base_models import BaseModel
from karrot.conversations.models import ConversationMixin


class Decision(BaseModel):
    """This is more like a decision _process_ than a decision..."""
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='decisions')
    ends_at = models.DateTimeField()


class Agreement(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='agreements')

    title = models.CharField(max_length=240)
    summary = models.TextField()
    content = models.TextField()

    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True)

    supersedes = models.ForeignKey('self', on_delete=models.CASCADE, null=True)


# - agreed_by? ... maybe a many through model... which could hold extra info
# - created_by? ... all users who contributed to the words?
# - replaces_agreement? replaced_by? parent?


class AgreementProposal(BaseModel, ConversationMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='agreement_proposals')

    decision = models.OneToOneField(Decision, on_delete=models.CASCADE, related_name='agreement_proposal')

    title = models.CharField(max_length=240)
    summary = models.TextField()
    content = models.TextField()

    supersedes = models.ForeignKey('self', on_delete=models.CASCADE, null=True)

    # if the proposal passes we need to supersede this one with a fresh one
    existing_agreement = models.OneToOneField(Agreement, on_delete=models.CASCADE, related_name='existing_proposal')

    # here's the one we created from this proposal (potentially)
    new_agreement = models.OneToOneField(Agreement, on_delete=models.CASCADE, null=True)

    # why somebody proposed it (optional)
    reason = models.TextField()
