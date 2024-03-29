# Generated by Django 3.2.7 on 2021-11-23 16:25

import django.contrib.postgres.fields
from django.db import migrations, models
import karrot.groups.models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0044_add_group_member_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupmembership',
            name='roles',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), default=karrot.groups.models.get_default_roles, size=None),
        ),
    ]
