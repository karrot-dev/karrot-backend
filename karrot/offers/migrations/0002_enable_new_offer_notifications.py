from django.db import migrations


class GroupNotificationType(object):
    NEW_OFFER = 'new_offer'


def enable_new_offer_notifications(apps, schema_editor):
    GroupMembership = apps.get_model('groups', 'GroupMembership')

    for membership in GroupMembership.objects.exclude(group__status='playground'):
        if GroupNotificationType.NEW_OFFER not in membership.notification_types:
            membership.notification_types.append(GroupNotificationType.NEW_OFFER)
            membership.save()


class Migration(migrations.Migration):
    dependencies = [
        ('offers', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(enable_new_offer_notifications, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
