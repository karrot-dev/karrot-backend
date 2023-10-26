from django.utils import timezone
from django.db import migrations

from karrot.history.models import HistoryTypus


def set_archived_at(apps, schema_editor):
    Offer = apps.get_model('offers', 'Offer')

    for offer in Offer.objects.filter(status='archived'):
        offer.archived_at = offer.status_changed_at
        offer.save()


class Migration(migrations.Migration):

    dependencies = [
        ('offers', '0005_offer_archived_at'),
    ]

    operations = [
        migrations.RunPython(set_archived_at, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
