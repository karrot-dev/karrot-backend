from enum import Enum

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class PlaceStatusOld(Enum):
    CREATED = 'created'
    NEGOTIATING = 'negotiating'
    ACTIVE = 'active'
    DECLINED = 'declined'
    ARCHIVED = 'archived'


def add_standard_place_statuses(apps, schema_editor):
    Group = apps.get_model('groups', 'Group')
    PlaceStatus = apps.get_model('places', 'PlaceStatus')
    Place = apps.get_model('places', 'Place')

    options = {
        'created': {
            'has_activities': False,
            'colour': '9E9E9E',  # quasar 'grey' rgb(158, 158, 158),
            'category': 'inactive',
        },
        'negotiating': {
            'has_activities': False,
            'colour': '2196F3',  # quasar 'blue' rgb(33, 150, 243)
            'category': 'inactive',
        },
        'active': {
            'has_activities': True,
            'colour': '21BA45',  # quasar 'positive' rgb(33, 186, 69)
            'category': 'active',
        },
        'declined': {
            'has_activities': False,
            'colour': 'DB2828',  # quasar 'negative' rgb(219, 40, 40)
            'category': 'inactive',
        },
        'archived': {
            'has_activities': False,
            'colour': '9E9E9E',  # quasar 'grey' rgb(158, 158, 158)
            'category': 'archived',
        }
    }

    for group in Group.objects.all():
        for status in [status.value for status in PlaceStatusOld]:
            options = options[status]
            status_next, _ = PlaceStatus.objects.get_or_create(
                group=group,
                name=status.capitalize(),
                defaults=options[status],
            )
            Place.objects.filter(group=group, status=status).update(status_next=status_next.id)





class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0043_auto_20200717_1325'),
        ('places', '0036_add_place_statuses'),
    ]

    operations = [
        migrations.RunPython(add_standard_place_statuses, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
