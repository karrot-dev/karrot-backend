# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-02-25 19:57
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0002_auto_20170222_1515'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='history',
            options={'ordering': ['-date']},
        ),
    ]
