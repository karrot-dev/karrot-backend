from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from foodsaving.cases.models import Voting


@db_periodic_task(crontab(minute='*'))  # every minute
def process_expired_votings():
    for voting in Voting.objects.filter(expires_at__lte=timezone.now(), accepted_option__isnull=True):
        voting.calculate_results()
