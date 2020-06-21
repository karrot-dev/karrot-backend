from datetime import timedelta

from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer
from karrot.webhooks.models import EmailEvent


@db_periodic_task(crontab(hour="*/12", minute=5))  # every 12 hours
def delete_old_email_events():
    with timer() as t:
        # delete email events after some months
        EmailEvent.objects.filter(
            created_at__lt=timezone.now() - timedelta(days=3 * 30)
        )

    stats_utils.periodic_task(
        "webhooks__delete_old_email_events", seconds=t.elapsed_seconds
    )
