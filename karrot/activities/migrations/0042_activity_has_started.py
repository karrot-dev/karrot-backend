# Generated by Django 4.2.7 on 2023-12-18 18:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0041_feedbacknoshow'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='has_started',
            field=models.BooleanField(default=False),
        ),
    ]
