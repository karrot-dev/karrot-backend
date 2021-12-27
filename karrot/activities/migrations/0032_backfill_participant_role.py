from django.db import migrations


def backfill_participant_type(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    ActivitySeries = apps.get_model('activities', 'ActivitySeries')

    for activity in Activity.objects.all():
        if activity.participant_types.count() == 0:
            participant_type = activity.participant_types.create(
                role='member',
                max_participants=activity.max_participants,
            )
            activity.activityparticipant_set.update(participant_type=participant_type)

    for series in ActivitySeries.objects.all():
        if series.participant_types.count() == 0:
            series.participant_types.create(
                role='member',
                max_participants=series.max_participants,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0031_add_participant_types'),
    ]

    operations = [
        migrations.RunPython(backfill_participant_type, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
