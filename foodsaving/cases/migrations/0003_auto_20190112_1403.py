# Generated by Django 2.1.5 on 2019-01-12 14:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0002_auto_20190109_2015'),
    ]

    operations = [
        migrations.RenameField(
            model_name='option',
            old_name='mean_score',
            new_name='sum_score',
        ),
        migrations.AlterField(
            model_name='option',
            name='type',
            field=models.TextField(choices=[('further_discussion', 'further_discussion'), ('no_change', 'no_change'), ('remove_user', 'remove_user')]),
        ),
        migrations.AlterField(
            model_name='vote',
            name='score',
            field=models.IntegerField(),
        ),
    ]