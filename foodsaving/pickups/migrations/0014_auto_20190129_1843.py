# Generated by Django 2.1.5 on 2019-01-29 18:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pickups', '0013_auto_20190122_1210'),
    ]

    operations = [
        migrations.RenameField(
            model_name='pickupdate',
            old_name='feedback_possible',
            new_name='is_done',
        ),
    ]
