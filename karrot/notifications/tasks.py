from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import IntegerField
from django.db.models.functions import Cast
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from karrot.issues.models import Voting, IssueStatus
from karrot.notifications.models import Notification, NotificationType
from karrot.activities.models import Activity, ActivityParticipant
from karrot.utils import stats_utils
from karrot.utils.stats_utils import timer


@db_periodic_task(crontab(minute='*'))  # every minute
def delete_expired_notifications():
    with timer() as t:
        Notification.objects.expired().delete()
    stats_utils.periodic_task('notifications__delete_expired_notifications', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute='*'))  # every minute
def create_activity_upcoming_notifications():
    # Oh oh, this is a bit complex. As notification.context is a JSONField, the participants_already_notified subquery
    # would return a jsonb object by default (which can't be compared to integer).
    # We can work around this by transforming the property value to text ("->>" lookup) and then casting to integer
    with timer() as t:
        participants_already_notified = Notification.objects.\
            order_by().\
            filter(type=NotificationType.ACTIVITY_UPCOMING.value).\
            exclude(context__activity_participant=None).\
            values_list(Cast(KeyTextTransform('activity_participant', 'context'), IntegerField()), flat=True)
        activities_due_soon = Activity.objects.order_by().due_soon()
        participants = ActivityParticipant.objects.\
            filter(activity__in=activities_due_soon).\
            exclude(id__in=participants_already_notified).\
            distinct()

        for participant in participants:
            Notification.objects.create(
                type=NotificationType.ACTIVITY_UPCOMING.value,
                user=participant.user,
                expires_at=participant.activity.date.start,
                context={
                    'group': participant.activity.place.group.id,
                    'place': participant.activity.place.id,
                    'activity': participant.activity.id,
                    'activity_participant': participant.id,
                },
            )

    stats_utils.periodic_task('notifications__create_activity_upcoming_notifications', seconds=t.elapsed_seconds)


@db_periodic_task(crontab(minute='*/5'))  # every five minutes
def create_voting_ends_soon_notifications():
    with timer() as t:
        existing_notifications = Notification.objects.order_by().filter(type=NotificationType.VOTING_ENDS_SOON.value
                                                                        ).values_list('user_id', 'context__issue')
        for voting in Voting.objects.order_by().due_soon().filter(issue__status=IssueStatus.ONGOING.value):
            # only notify users that haven't voted already
            for user in voting.issue.group.members.exclude(votes_given__option__voting=voting):
                if (user.id, voting.issue_id) not in existing_notifications:
                    Notification.objects.create(
                        type=NotificationType.VOTING_ENDS_SOON.value,
                        user=user,
                        expires_at=voting.expires_at,
                        context={
                            'group': voting.issue.group_id,
                            'issue': voting.issue_id,
                        },
                    )

    stats_utils.periodic_task('notifications__create_voting_ends_soon_notification', seconds=t.elapsed_seconds)
