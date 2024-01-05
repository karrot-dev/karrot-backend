"""Moves place statuses from enum type into foreign key type"""


from django.db import migrations
from fractional_indexing import generate_key_between


_last_order = None


def next_order():
    global _last_order
    order = generate_key_between(_last_order, None)
    _last_order = order
    return order


# Default types that will be created for new groups
# (in the future this would be more customizable)
default_place_statuses = {
    'Created': {
        'name_is_translatable': True,
        'colour': '9e9e9e',
        'is_visible': True,
        'order': next_order(),
    },
    'Negotiating': {
        'name_is_translatable': True,
        'colour': '2196f3',
        'is_visible': True,
        'order': next_order(),
    },
    'Active': {
        'name_is_translatable': True,
        'colour': '21BA45',
        'is_visible': True,
        'order': next_order(),
    },
    'Declined': {
        'name_is_translatable': True,
        'colour': 'DB2828',
        'is_visible': False,
        'order': next_order(),
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

        # update anything without a status_next to be created (which should just be previously archived ones)
        created_place_status = PlaceStatus.objects.get(group=group, name='Created')
        Place.objects.filter(group=group, status_next__isnull=True).update(status_next=created_place_status)


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('places', '0043_placetype_description_placestatus_place_status_next'),
    ]

    operations = [
        migrations.RunPython(migrate_place_statuses, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
