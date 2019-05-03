from dateutil.relativedelta import relativedelta
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models import Count
from django.utils import timezone

from config import settings
from karrot.base.base_models import BaseModel


class EmailEventQuerySet(models.QuerySet):
    def ignored(self):
        return self.filter(
            created_at__gte=timezone.now() - relativedelta(months=3), event__in=settings.EMAIL_EVENTS_AVOID
        )

    def ignored_addresses(self):
        return self.ignored().values('address').annotate(count=Count('id')).filter(count__gte=5).values('address')

    def for_user(self, user):
        return self.ignored().filter(address=user.email)


class EmailEvent(BaseModel):
    objects = EmailEventQuerySet.as_manager()

    id = models.BigAutoField(primary_key=True)
    address = models.TextField()
    event = models.CharField(max_length=255)
    payload = JSONField()


class IncomingEmail(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.ForeignKey('conversations.ConversationMessage', on_delete=models.CASCADE)

    payload = JSONField()
