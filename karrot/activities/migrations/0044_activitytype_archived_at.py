# Generated by Django 4.2.1 on 2023-10-26 11:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0043_set_activity_has_started'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitytype',
            name='archived_at',
            field=models.DateTimeField(null=True),
        ),
    ]
