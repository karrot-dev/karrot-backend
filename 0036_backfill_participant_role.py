from django.db import migrations


def backfill_participant_type(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    ParticipantType = apps.get_model('activities', 'ParticipantType')

    for activity in Activity.objects.all():
        participant_type = ParticipantType.objects.create(role='member', max_participants=activity.max_participants)
        for participant in activity.participants.all():
            participant.participant_type = participant_type
            participant.save()


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0035_auto_20211123_1625'),
    ]

    operations = [
        migrations.RunPython(backfill_participant_type, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
