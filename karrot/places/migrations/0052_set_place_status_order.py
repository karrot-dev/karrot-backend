"""Moves place statuses from enum type into foreign key type"""


from django.utils import timezone
from django.db import migrations

from fractional_indexing import generate_n_keys_between


def set_place_status_order(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    PlaceStatus = apps.get_model('places', 'PlaceStatus')
    for group in Group.objects.all():
        place_statuses = list(PlaceStatus.objects.filter(group=group).order_by('order', 'id'))
        orders = generate_n_keys_between(None, None, n=len(place_statuses))
        for index, place_status in enumerate(place_statuses):
            place_status.order = orders[index]
        PlaceStatus.objects.bulk_update(place_statuses, ['order'])


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('places', '0051_alter_placestatus_options'),
    ]

    operations = [
        migrations.RunPython(set_place_status_order, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
