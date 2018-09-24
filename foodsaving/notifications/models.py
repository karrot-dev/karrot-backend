from enum import Enum

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models

from foodsaving.base.base_models import BaseModel
from foodsaving.notifications import stats


class NotificationType(Enum):
    NEW_APPLICANT = 'new_applicant'
    APPLICATION_ACCEPTED = 'application_accepted'
    APPLICATION_DECLINED = 'application_declined'
    USER_BECAME_EDITOR = 'user_became_editor'
    YOU_BECAME_EDITOR = 'you_became_editor'
    FEEDBACK_POSSIBLE = 'feedback_possible'
    NEW_STORE = 'new_store'
    NEW_MEMBER = 'new_member'
    INVITATION_ACCEPTED = 'invitation_accepted'
    PICKUP_UPCOMING = 'pickup_upcoming'


class Notification(BaseModel):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=255)
    context = JSONField(null=True)
    expires_at = models.DateTimeField(null=True)
    clicked = models.BooleanField(default=False)

    def save(self, **kwargs):
        old = type(self).objects.get(pk=self.pk) if self.pk else None
        super().save(**kwargs)
        if old is None:
            stats.notification_created(self)
        elif self.clicked and not old.clicked:
            stats.notification_clicked(self)


class NotificationMeta(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(null=True)
