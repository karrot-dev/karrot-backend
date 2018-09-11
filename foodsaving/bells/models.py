from enum import Enum

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models

from foodsaving.base.base_models import BaseModel


class BellType(Enum):
    NEW_APPLICANT = 'new_applicant'
    APPLICATION_ACCEPTED = 'application_accepted'
    APPLICATION_DECLINED = 'application_declined'
    USER_BECAME_EDITOR = 'user_became_editor'
    FEEDBACK_POSSIBLE = 'feedback_possible'
    NEW_STORE = 'new_store'
    """
    - pickup gets created/modified/deleted
    - pickup series get created/modified/deleted
    - store changed
    - new feedback
    - pickup_upcoming (maybe better from state)
    """


class BellQuerySet(models.QuerySet):
    pass


class Bell(BaseModel):
    objects = BellQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=255)
    payload = JSONField(null=True)
    expires_at = models.DateTimeField(null=True)
