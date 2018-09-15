from enum import Enum

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.manager import BaseManager

from foodsaving.base.base_models import BaseModel, NicelyFormattedModel


class NotificationType(Enum):
    NEW_APPLICANT = 'new_applicant'
    APPLICATION_ACCEPTED = 'application_accepted'
    APPLICATION_DECLINED = 'application_declined'
    USER_BECAME_EDITOR = 'user_became_editor'
    FEEDBACK_POSSIBLE = 'feedback_possible'
    NEW_STORE = 'new_store'
    NEW_MEMBER = 'new_member'
    INVITATION_ACCEPTED = 'invitation_accepted'
    """
    - new trust (stackable!)
    - pickup_upcoming (maybe better from state)
    
    needs store subscription
    - pickup gets created/modified/deleted
    - pickup series get created/modified/deleted
    - store changed
    - new feedback
    """


class NotificationQuerySet(models.QuerySet):
    pass


class NotificationManager(BaseManager.from_queryset(NotificationQuerySet)):
    pass


class Notification(BaseModel):
    objects = NotificationManager()

    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=255)
    context = JSONField(null=True)
    expires_at = models.DateTimeField(null=True)
    clicked_at = models.DateTimeField(null=True)

    def clicked(self):
        return self.clicked_at is not None


class NotificationMeta(NicelyFormattedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(null=True)
