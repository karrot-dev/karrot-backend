# Generated by Django 4.2.1 on 2023-10-26 11:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('offers', '0004_auto_20200110_1702'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='archived_at',
            field=models.DateTimeField(null=True),
        ),
    ]
