from datetime import timedelta

from django.db import migrations
from django.db.models import Func, F


def populate_date_range(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')

    # initializes the date_range field with a range of (date, date + 30 minutes)
    Activity.objects.all().update(
        date_range=Func(F('date'), F('date') + timedelta(minutes=30), function='tstzrange')
    )


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0010_activity_date_range'),
    ]

    operations = [
        migrations.RunPython(populate_date_range, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
