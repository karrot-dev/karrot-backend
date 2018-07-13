# Generated by Django 2.0.7 on 2018-07-13 20:17

from django.db import migrations


class GroupNotificationType(object):
    WEEKLY_SUMMARY = 'weekly_summary'
    DAILY_PICKUP_NOTIFICATION = 'daily_pickup_notification'
    NEW_APPLICATION = 'new_application'


def enable_new_application_notifications(apps, schema_editor):
    GroupMembership = apps.get_model('groups', 'GroupMembership')

    for membership in GroupMembership.objects.all():
        membership.notification_types.append(GroupNotificationType.NEW_APPLICATION)
        membership.save()


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0033_auto_20180713_1814'),
    ]

    operations = [
        migrations.RunPython(enable_new_application_notifications, reverse_code=migrations.RunPython.noop),
    ]
