# Generated by Django 3.0.9 on 2020-08-17 08:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0021_make_activity_typus_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitytype',
            name='feedback',
            field=models.BooleanField(default=True),
        ),
    ]
