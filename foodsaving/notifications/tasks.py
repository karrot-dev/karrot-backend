from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from foodsaving.notifications.models import Notification


@db_periodic_task(crontab(minute='*'))  # every minute
def delete_expired_notifications():
    Notification.objects.filter(expires_at__gte=timezone.now()).delete()
