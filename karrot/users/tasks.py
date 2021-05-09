from huey import crontab
from huey.contrib.djhuey import db_periodic_task
from karrot.utils.influxdb_utils import write_points

from karrot.users.stats import get_users_stats, get_user_language_stats
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


@db_periodic_task(crontab(hour='*/6', minute=5))  # every 6 hours
def record_user_stats():
    with timer() as t:
        fields = get_users_stats()
        language_fields = get_user_language_stats()

        write_points([{
            'measurement': 'karrot.users',
            'fields': fields,
        }])

        write_points([{
            'measurement': 'karrot.users.language',
            'fields': language_fields,
        }])

    stats_utils.periodic_task('users__record_user_stats', seconds=t.elapsed_seconds)
