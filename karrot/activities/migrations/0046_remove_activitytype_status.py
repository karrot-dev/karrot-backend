# Generated by Django 4.2.1 on 2023-10-26 22:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0045_set_activity_type_archived_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='activitytype',
            name='status',
        ),
    ]
