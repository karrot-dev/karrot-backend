# Generated by Django 2.1.1 on 2018-09-15 17:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notificationmeta'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='clicked_at',
            field=models.DateTimeField(null=True),
        ),
    ]
