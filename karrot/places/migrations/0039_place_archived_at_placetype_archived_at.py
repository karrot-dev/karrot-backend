# Generated by Django 4.2.1 on 2023-10-26 11:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0038_place_default_view'),
    ]

    operations = [
        migrations.AddField(
            model_name='place',
            name='archived_at',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='placetype',
            name='archived_at',
            field=models.DateTimeField(null=True),
        ),
    ]