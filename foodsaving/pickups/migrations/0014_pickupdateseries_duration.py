# Generated by Django 2.1.5 on 2019-01-30 16:15

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pickups', '0013_auto_20190122_1210'),
    ]

    operations = [
        migrations.AddField(
            model_name='pickupdateseries',
            name='duration',
            field=models.DurationField(default=datetime.timedelta(seconds=1800)),
        ),
    ]
