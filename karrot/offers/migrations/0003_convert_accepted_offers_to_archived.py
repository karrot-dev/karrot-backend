from django.db import migrations


def convert_accepted_offers_to_archived(apps, schema_editor):
    Offer = apps.get_model('offers', 'Offer')

    Offer.objects.filter(status='accepted').update(status='archived')


class Migration(migrations.Migration):
    dependencies = [
        ('offers', '0002_enable_new_offer_notifications'),
    ]

    operations = [
        migrations.RunPython(convert_accepted_offers_to_archived, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
