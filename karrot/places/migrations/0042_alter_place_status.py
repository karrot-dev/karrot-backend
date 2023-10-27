# Generated by Django 4.2.1 on 2023-10-27 00:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0041_remove_placetype_status_alter_place_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='place',
            name='status',
            field=models.CharField(choices=[('created', 'Created'), ('negotiating', 'Negotiating'), ('active', 'Active'), ('declined', 'Declined'), ('archived', 'Archived')], default='created', max_length=20),
        ),
    ]
