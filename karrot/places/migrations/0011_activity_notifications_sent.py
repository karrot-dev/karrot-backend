# Generated by Django 1.11.2 on 2017-06-28 22:26

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0010_auto_20170223_1657'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='notifications_sent',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
    ]
