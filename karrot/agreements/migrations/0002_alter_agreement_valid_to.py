# Generated by Django 3.2.15 on 2022-09-26 22:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agreements', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agreement',
            name='valid_to',
            field=models.DateTimeField(null=True),
        ),
    ]
