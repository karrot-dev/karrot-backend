# Generated by Django 2.1.5 on 2019-01-09 14:04

from django.db import migrations
import versatileimagefield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0035_groupmembership_removal_notification_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='photo',
            field=versatileimagefield.fields.VersatileImageField(null=True, upload_to='group_photos', verbose_name='Group Photo'),
        ),
    ]
