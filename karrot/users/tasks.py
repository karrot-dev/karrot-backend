from huey import crontab
from huey.contrib.djhuey import db_periodic_task
from influxdb_metrics.loader import write_points

from karrot.users.stats import get_users_stats
from karrot.utils import stats_utils


@db_periodic_task(crontab(hour='*/6', minute=5))  # every 6 hours
def record_user_stats():
    stats_utils.periodic_task('users__record_user_stats')

    fields = get_users_stats()

    write_points([{
        'measurement': 'karrot.users',
        'fields': fields,
    }])
