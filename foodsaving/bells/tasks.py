from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from foodsaving.bells.models import Bell


@db_periodic_task(crontab(minute='*'))  # every minute
def delete_expired_bells():
    Bell.objects.filter(expires_at__gte=timezone.now()).delete()
