from django.db import migrations


def add_task_activity_type(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    ActivityType = apps.get_model('activities', 'ActivityType')
    Activity = apps.get_model('activities', 'Activity')
    ActivitySeries = apps.get_model('activities', 'ActivitySeries')

    for group in Group.objects.exclude(theme='foodsaving'):
        activity_type, _ = ActivityType.objects.get_or_create(
            group=group,
            name='Task',
            defaults={
                'colour': '455a64',
                'icon': 'fas fa-check-circle',
                'feedback_icon': 'fas fa-reply',
                'has_feedback': True,
                'has_feedback_weight': False,
            },
        )
        Activity.objects.filter(place__group=group).update(activity_type=activity_type.id)
        ActivitySeries.objects.filter(place__group=group).update(activity_type=activity_type.id)


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0025_activitytype_name_is_translatable'),
    ]

    operations = [
        migrations.RunPython(add_task_activity_type, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
