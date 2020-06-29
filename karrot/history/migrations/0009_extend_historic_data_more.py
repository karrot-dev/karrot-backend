from django.db import migrations

BATCH_SIZE = 1000


def migrate(apps, schema_editor):
    History = apps.get_model('history', 'History')

    # rewrite activity payload date field from string to list
    save_payload = []

    for h in History.objects.filter(payload__date__0__isnull=True, payload__date__isnull=False):
        h.payload['date'] = [h.payload['date']]
        save_payload.append(h)

    History.objects.bulk_update(save_payload, fields=['payload'], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0008_extend_historic_data'),
    ]

    operations = [migrations.RunPython(migrate, migrations.RunPython.noop, elidable=True)]
