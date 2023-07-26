import django.contrib.postgres.fields
from django.db import migrations, models
import karrot.groups.models


def enable_agreements_and_participant_types(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')

    for group in Group.objects.all():
        changed = False
        for feature in ['agreements', 'participant-types']:
            if feature not in group.features:
                group.features.append(feature)
                changed = True
        if changed:
            group.save()


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0049_auto_20220930_1506'),
    ]

    operations = [
        migrations.RunPython(enable_agreements_and_participant_types, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
