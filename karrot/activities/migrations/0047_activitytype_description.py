# Generated by Django 4.2.7 on 2023-12-05 14:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0046_remove_activitytype_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitytype',
            name='description',
            field=models.TextField(blank=True),
        ),
    ]
