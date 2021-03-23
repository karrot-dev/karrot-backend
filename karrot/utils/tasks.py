from huey import crontab
from huey.contrib.djhuey import periodic_task

from karrot.utils.influxdb_utils import flush_stats


@periodic_task(crontab(minute='*'))  # every minute
def flush_stats_periodic():
    flush_stats()
