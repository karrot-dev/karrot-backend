# Generated by Django 2.2.5 on 2019-09-18 12:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0004_auto_20190914_0724'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailevent',
            name='version',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='incomingemail',
            name='version',
            field=models.IntegerField(),
        ),
    ]
