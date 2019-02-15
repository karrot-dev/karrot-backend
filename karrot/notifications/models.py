from django.db.models.manager import BaseManager
from django.utils import timezone
from enum import Enum

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models

from karrot.base.base_models import BaseModel
from karrot.notifications import stats


class NotificationType(Enum):
    NEW_APPLICANT = 'new_applicant'
    APPLICATION_ACCEPTED = 'application_accepted'
    APPLICATION_DECLINED = 'application_declined'
    USER_BECAME_EDITOR = 'user_became_editor'
    YOU_BECAME_EDITOR = 'you_became_editor'
    FEEDBACK_POSSIBLE = 'feedback_possible'
    NEW_PLACE = 'new_place'
    NEW_MEMBER = 'new_member'
    INVITATION_ACCEPTED = 'invitation_accepted'
    PICKUP_UPCOMING = 'pickup_upcoming'
    PICKUP_DISABLED = 'pickup_disabled'
    PICKUP_ENABLED = 'pickup_enabled'
    PICKUP_MOVED = 'pickup_moved'
    CONFLICT_RESOLUTION_CREATED = 'conflict_resolution_created'
    CONFLICT_RESOLUTION_CREATED_ABOUT_YOU = 'conflict_resolution_created_about_you'
    CONFLICT_RESOLUTION_CONTINUED = 'conflict_resolution_continued'
    CONFLICT_RESOLUTION_CONTINUED_ABOUT_YOU = 'conflict_resolution_continued_about_you'
    CONFLICT_RESOLUTION_DECIDED = 'conflict_resolution_decided'
    CONFLICT_RESOLUTION_DECIDED_ABOUT_YOU = 'conflict_resolution_decided_about_you'
    CONFLICT_RESOLUTION_YOU_WERE_REMOVED = 'conflict_resolution_you_were_removed'
    VOTING_ENDS_SOON = 'voting_ends_soon'


class NotificationQuerySet(models.QuerySet):
    def expired(self):
        return self.filter(expires_at__lte=timezone.now())

    def not_expired(self):
        return self.exclude(expires_at__lte=timezone.now())


class NotificationManager(BaseManager.from_queryset(NotificationQuerySet)):
    def create_for_pickup_collectors(self, collectors, type):
        for collector in collectors:
            pickup = collector.pickupdate
            super().create(
                user=collector.user,
                type=type,
                context={
                    'group': pickup.group.id,
                    'place': pickup.place.id,
                    'pickup': pickup.id,
                    'pickup_collector': collector.id,
                }
            )


class Notification(BaseModel):
    objects = NotificationManager()

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
