from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from karrot.invitations.models import Invitation


@db_periodic_task(crontab(minute=0))  # every hour
def delete_expired_invitations():
    Invitation.objects.delete_expired_invitations()
