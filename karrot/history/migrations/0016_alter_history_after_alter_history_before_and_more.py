# Generated by Django 4.2.7 on 2023-11-29 09:03

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
    ]

    operations = [
        migrations.AlterField(
            model_name='history',
            name='after',
            field=models.JSONField(encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
        migrations.AlterField(
            model_name='history',
            name='before',
            field=models.JSONField(encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
        migrations.AlterField(
            model_name='history',
            name='payload',
            field=models.JSONField(encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
    ]
