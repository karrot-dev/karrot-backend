# Generated by Django 4.2.7 on 2024-01-03 21:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0046_rename_status_next_place_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='place',
            name='status',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='places', to='places.placestatus'),
        ),
    ]
