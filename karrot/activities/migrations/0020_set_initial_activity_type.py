# Generated by Django 3.0.9 on 2020-08-16 20:47

from django.db import migrations


def set_initial_activity_type(apps, schema_editor):
    ActivityType = apps.get_model('activities', 'ActivityType')
    Activity = apps.get_model('activities', 'Activity')

    pickup_type, _ = ActivityType.objects.get_or_create(
        name='pickup',
        defaults={
            'colour': 1,
            'icon': 'basket',
            'feedback': True,
            'feedback_has_weight': True,
        },
    )

    activity_type, _ = ActivityType.objects.get_or_create(
        name='activity',
        defaults={
            'colour': 2,
            'icon': 'foo',
            'feedback': True,
            'feedback_has_weight': False,
        },
    )

    Activity.objects.filter(place__group__theme='foodsaving').update(typus=pickup_type.id)
    # TODO: should bikekitchen "activities" turn into "pickups" or "activities"?
    Activity.objects.exclude(place__group__theme='foodsaving').update(typus=activity_type.id)


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0019_add_activity_types'),
    ]

    operations = [
        migrations.RunPython(set_initial_activity_type, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
