from dateutil.relativedelta import relativedelta
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.postgres.fields import JSONField
from django.db.models import CharField, TextField, BigAutoField, Count
from django.utils import timezone

from config import settings
from foodsaving.base.base_models import BaseModel


class EmailEventManager(BaseUserManager):

    def ignored(self):
        return self.filter(
            created_at__gte=timezone.now() - relativedelta(months=3),
            event__in=settings.EMAIL_EVENTS_AVOID
        )

    def ignored_addresses(self):
        # return []
        return self.ignored().values('address').annotate(count=Count('id')).filter(count__gte=5).values('address')

    def for_user(self, user):
        return self.ignored().filter(
            address=user.address
        )


class EmailEvent(BaseModel):
    objects = EmailEventManager()

    id = BigAutoField(primary_key=True)
    address = TextField()
    event = CharField(max_length=255)
    payload = JSONField()
