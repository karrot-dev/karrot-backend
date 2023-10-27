"""Moves place statuses from enum type into foreign key type"""


from django.utils import timezone
from django.db import migrations

from karrot.history.models import HistoryTypus

default_place_statuses = {
    'Created': {
        'colour': '9e9e9e',
    },
    'Negotiating': {
        'colour': '2196f3',
    },
    'Active': {
        'colour': '21BA45',
    },
    'Declined': {
        'colour': 'DB2828'
    },
}


def migrate_place_statuses(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    Place = apps.get_model('places', 'Place')
    PlaceStatus = apps.get_model('places', 'PlaceStatus')
    # ensure we have the default statuses
    for group in Group.objects.all():
        for name, options in default_place_statuses.items():
            PlaceStatus.objects.get_or_create(name=name, group=group, defaults=options)

        # update all the existing place statuses to use the new column
        for (from_status, to_status_name) in [
            ('created', 'Created'),
            ('negotiating', 'Negotiating'),
            ('active', 'Active'),
            ('declined', 'Declined'),
        ]:
            place_status = PlaceStatus.objects.get(group=group, name=to_status_name)
            Place.objects.filter(group=group, status=from_status).update(status_next=place_status)


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('places', '0043_placetype_description_placestatus_place_status_next'),
    ]

    operations = [
        migrations.RunPython(migrate_place_statuses, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
