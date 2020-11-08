from anymail.signals import EventType
from django.db.models import JSONField
from django.db import models

from config import settings
from karrot.base.base_models import BaseModel


class EmailEventQuerySet(models.QuerySet):
    def failed_for_user(self, user):
        return self.filter(address=user.email, event__in=[EventType.BOUNCED, EventType.FAILED, EventType.REJECTED])


class EmailEvent(BaseModel):
    objects = EmailEventQuerySet.as_manager()

    id = models.BigAutoField(primary_key=True)
    address = models.TextField()
    event = models.CharField(max_length=255)
    payload = JSONField()
    version = models.IntegerField()

    @property
    def reason(self):
        if self.version == 2:
            return self.payload['payload']['output']
        return self.payload.get('reason')

    @property
    def subject(self):
        if self.version == 2:
            return self.payload['payload']['message']['subject']
        return self.payload.get('subject')


class IncomingEmail(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.ForeignKey('conversations.ConversationMessage', on_delete=models.CASCADE)

    payload = JSONField()
    version = models.IntegerField()
