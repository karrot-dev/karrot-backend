# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-08-01 23:59
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0003_auto_20160728_1725'),
    ]

    operations = [
        migrations.AlterField(
            model_name='group',
            name='members',
            field=models.ManyToManyField(related_name='groups', to=settings.AUTH_USER_MODEL),
        ),
    ]
