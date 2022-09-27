from django.db import models

from karrot.base.base_models import BaseModel


class Agreement(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='agreements')

    title = models.CharField(max_length=240)
    summary = models.TextField()
    content = models.TextField()

    active_from = models.DateTimeField()
    active_until = models.DateTimeField(null=True)
    review_at = models.DateTimeField(null=True)


#
#
# class AgreementProposal(BaseModel, ConversationMixin):
#     group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='agreement_proposals')
#
#     title = models.CharField(max_length=240)
#     summary = models.TextField()
#     content = models.TextField()
#
#     #
#     agreement = models.OneToOneField(Agreement, on_delete=models.CASCADE, related_name='agreement')
#
#     # why somebody proposed it (optional)
#     reason = models.TextField()
