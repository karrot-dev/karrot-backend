# Generated by Django 2.0.3 on 2018-04-07 18:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0011_auto_20180303_1748'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationmessage',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
