# Generated by Django 1.11.5 on 2017-09-07 14:06

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0022_auto_20170901_1732'),
    ]

    operations = [
        migrations.AlterField(
            model_name='feedback',
            name='weight',
            field=models.FloatField(blank=True, null=True,
                                    validators=[django.core.validators.MinValueValidator(0),
                                                django.core.validators.MaxValueValidator(10000)]),
        ),
    ]
