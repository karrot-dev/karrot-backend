from django.db import migrations


def add_standard_place_types(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    PlaceType = apps.get_model('places', 'PlaceType')
    Place = apps.get_model('places', 'Place')

    for group in Group.objects.all():

        if group.theme == 'foodsaving':
            place_type, _ = PlaceType.objects.get_or_create(
                group=group,
                name='Store',
                defaults={
                    'icon': 'fas fa-shopping-cart'
                },
            )
        else:
            place_type, _ = PlaceType.objects.get_or_create(
                group=group,
                name='Place',  # what is a good generic name? Location, Place, ..., ?
                defaults={
                    'icon': 'fas fa-dot-circle'
                },
            )

        Place.objects.filter(group=group).update(place_type=place_type.id)


class Migration(migrations.Migration):
    dependencies = [
        ('groups', '0043_auto_20200717_1325'),
        ('places', '0034_add_place_types'),
    ]

    operations = [
        migrations.RunPython(add_standard_place_types, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
