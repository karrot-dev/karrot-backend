# Generated by Django 2.1.5 on 2019-01-22 12:10

from django.db import migrations
import foodsaving.pickups.models


class Migration(migrations.Migration):

    dependencies = [
        ('pickups', '0012_rename_date_range_to_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pickupdate',
            name='date',
            field=foodsaving.pickups.models.CustomDateTimeRangeField(default=foodsaving.pickups.models.default_pickup_date_range),
        ),
    ]
