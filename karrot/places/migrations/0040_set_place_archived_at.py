from django.utils import timezone
from django.db import migrations

from karrot.history.models import HistoryTypus


def set_archived_at(apps, schema_editor):
    Place = apps.get_model('places', 'Place')
    PlaceType = apps.get_model('places', 'PlaceType')
    History = apps.get_model('history', 'History')

    for place in Place.objects.filter(status='archived'):
        # find the date it was (last) archived if possible
        history = History.objects.filter(
            typus=HistoryTypus.STORE_MODIFY,
            payload__status='archived',
            before__id=place.id,
        ).order_by('date').last()
        place.archived_at = history.date if history else timezone.now()
        place.save()

    for place_type in PlaceType.objects.filter(status='archived'):
        # find the date it was (last) archived if possible
        history = History.objects.filter(
            typus=HistoryTypus.PLACE_TYPE_MODIFY,
            payload__status='archived',
            before__id=place_type.id,
        ).order_by('date').last()
        place_type.archived_at = history.date if history else timezone.now()
        place_type.save()



class Migration(migrations.Migration):

    dependencies = [
        ('places', '0039_place_archived_at_placetype_archived_at'),
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
    ]

    operations = [
        migrations.RunPython(set_archived_at, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
