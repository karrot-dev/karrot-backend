from dateutil.parser import parse
from django.db import migrations
from django.utils import timezone


def keep_moved_pickups(apps, schema_editor):
    PickupDate = apps.get_model('pickups', 'PickupDate')
    History = apps.get_model('history', 'History')

    message = """Message from Karrot:
This is a placeholder for a pickup that was moved.
The pickup still exists and has been converted into a one-time pickup."""

    moved_pickups = PickupDate.objects.filter(is_date_changed=True, date__gte=timezone.now())
    for pickup in moved_pickups:
        first_date_change = History.objects.filter(typus=8, before__id=pickup.id, before__is_date_changed=False,
                                                   after__is_date_changed=True).first()
        original_date = parse(first_date_change.before['date'])
        series = pickup.series

        PickupDate.objects.create(
            date=original_date,
            max_collectors=series.max_collectors,
            series=series,
            place=series.place,
            description=message,
            deleted=True,
        )

        pickup.series = None
        pickup.save()


class Migration(migrations.Migration):
    dependencies = [
        ('pickups', '0005_pickupdate_feedback_given_by'),
    ]

    operations = [
        migrations.RunPython(keep_moved_pickups, migrations.RunPython.noop, elidable=True)
    ]
