from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_participant_role(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    ParticipantRole = apps.get_model('activities', 'ParticipantRole')

    for activity in Activity.objects.all():
        participant_role = ParticipantRole.objects.create(role='member', max_participants=activity.max_participants)
        for participant in activity.participants.all():
            participant.participant_role = participant_role
            participant.save()


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0035_auto_20211123_1625'),
    ]

    operations = [
        migrations.RunPython(backfill_participant_role, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
