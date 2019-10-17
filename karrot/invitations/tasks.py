from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from karrot.invitations.models import Invitation
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


@db_periodic_task(crontab(minute=0))  # every hour
def delete_expired_invitations():
    with timer() as t:
        Invitation.objects.delete_expired_invitations()

    stats_utils.periodic_task('invitations__deleted_expired_invitations', seconds=t.elapsed_seconds)
