# Generated by Django 2.0.7 on 2018-07-17 15:16

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conversations', '0015_auto_20180717_0935'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='conversationthreadparticipant',
            unique_together={('user', 'message')},
        ),
    ]
