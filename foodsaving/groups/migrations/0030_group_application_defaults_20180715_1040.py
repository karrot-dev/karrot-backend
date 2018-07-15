# Generated by Django 2.0.7 on 2018-07-15 10:40
from enum import Enum

from django.db import migrations, models


class GroupStatus(Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    PLAYGROUND = 'playground'


def migrate_playground_groups_to_be_open(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    Group.objects.filter(status=GroupStatus.PLAYGROUND.value).update(is_open=True)


def migrate_unprotected_groups_to_be_open(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    Group.objects.filter(password='').update(is_open=True)

class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0029_group_last_active_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='application_questions',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='group',
            name='is_open',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(migrate_playground_groups_to_be_open, reverse_code=migrations.RunPython.noop, elidable=True),
        migrations.RunPython(migrate_unprotected_groups_to_be_open, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
