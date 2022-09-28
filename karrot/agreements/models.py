from django.conf import settings
from django.db import models

from karrot.base.base_models import BaseModel


class Agreement(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='agreements')

    title = models.CharField(max_length=240)
    summary = models.TextField(null=True, blank=True)
    content = models.TextField()

    active_from = models.DateTimeField()
    active_until = models.DateTimeField(null=True)
    review_at = models.DateTimeField(null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='agreements_created',
        null=True,
    )
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='changed_agreements',
        null=True,
    )
