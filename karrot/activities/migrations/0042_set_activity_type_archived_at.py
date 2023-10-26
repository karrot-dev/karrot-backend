from django.utils import timezone
from django.db import migrations

from karrot.history.models import HistoryTypus


def set_archived_at(apps, schema_editor):
    ActivityType = apps.get_model('activities', 'ActivityType')
    History = apps.get_model('history', 'History')

    for activity_type in ActivityType.objects.filter(status='archived'):
        # find the date it was (last) archived if possible
        history = History.objects.filter(
            typus=HistoryTypus.ACTIVITY_TYPE_MODIFY,
            payload__status='archived',
            before__id=activity_type.id,
        ).order_by('date').last()
        activity_type.archived_at = history.date if history else timezone.now()
        activity_type.save()


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0041_activitytype_archived_at'),
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
    ]

    operations = [
        migrations.RunPython(set_archived_at, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
