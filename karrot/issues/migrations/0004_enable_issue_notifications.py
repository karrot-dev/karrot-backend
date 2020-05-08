from django.db import migrations, models


def enable_issue_notifications(apps, schema_editor):
    GroupMembership = apps.get_model('groups', 'GroupMembership')
    for membership in GroupMembership.objects.exclude(notification_types__contains=['conflict_resolution']):
        membership.notification_types.append('conflict_resolution')
        membership.save()


class Migration(migrations.Migration):

    dependencies = [
        ('issues', '0003_issue_status_changed_at'),
    ]

    operations = [migrations.RunPython(enable_issue_notifications, migrations.RunPython.noop, elidable=True)]
