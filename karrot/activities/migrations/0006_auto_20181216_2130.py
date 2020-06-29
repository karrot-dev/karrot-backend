from dateutil.parser import parse
from django.db import migrations
from django.utils import timezone


def keep_moved_activities(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    History = apps.get_model('history', 'History')

    message = """Message from Karrot:
This is a placeholder for an activity that was moved.
The activity still exists and has been converted into a one-time activity."""

    moved_activities = Activity.objects.filter(is_date_changed=True, date__gte=timezone.now())
    for activity in moved_activities:
        first_date_change = History.objects.filter(typus=8, before__id=activity.id, before__is_date_changed=False,
                                                   after__is_date_changed=True).first()
        original_date = parse(first_date_change.before['date'])
        series = activity.series

        Activity.objects.create(
            date=original_date,
            max_participants=series.max_participants,
            series=series,
            place=series.place,
            description=message,
            deleted=True,
        )

        activity.series = None
        activity.save()


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0005_activity_feedback_given_by'),
    ]

    operations = [
        migrations.RunPython(keep_moved_activities, migrations.RunPython.noop, elidable=True)
    ]
