# Generated by Django 2.1.5 on 2019-01-08 21:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0034_auto_20180806_1428'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupmembership',
            name='removal_notification_at',
            field=models.DateTimeField(null=True),
        ),
    ]