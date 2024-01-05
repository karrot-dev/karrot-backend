from django.db import migrations
from django.db.models import Count, F

from karrot.history.models import HistoryTypus


def fix_activity_done_missed_history(apps, schema_editor):
    """ Fix issue caused by processing finished activities after start

    We previously processed finished activities right after they *started*
    BUT allowed people to join after they had started...

    So if somebody joined after it started we might either have:
        a) the wrong count of users on the history object
        b) the wrong history typus (if 0 users before, it'd be marked as MISSED, not DONE)

    This data migration fixes those historic issues.
    """

    History = apps.get_model('history', 'History')

    # Update users for ACTIVITY_DONE if there are more activity participants than history users
    for history in History.objects \
        .filter(typus=HistoryTypus.ACTIVITY_DONE) \
        .exclude(activity=None) \
        .annotate(
            history_user_count=Count('users', distinct=True),
            activity_user_count=Count('activity__participants', distinct=True),
        ).filter(activity_user_count__gt=F('history_user_count')).iterator():
        history.users.set(history.activity.participants.all())

    # Convert ACTIVITY_MISSED to ACTIVITY_DONE if there were actually participants
    for history in History.objects \
        .filter(typus=HistoryTypus.ACTIVITY_MISSED) \
        .exclude(activity=None) \
        .annotate(activity_user_count=Count('activity__participants', distinct=True)) \
        .filter(activity_user_count__gt=0).iterator():
        history.typus = HistoryTypus.ACTIVITY_DONE
        history.save()
        history.users.set(history.activity.participants.all())


class Migration(migrations.Migration):
    dependencies = [
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
    ]

    operations = [
        migrations.RunPython(fix_activity_done_missed_history, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
