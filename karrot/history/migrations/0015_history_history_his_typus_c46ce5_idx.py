# Generated by Django 4.2.1 on 2023-09-02 00:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0014_history_agreement'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='history',
            index=models.Index(fields=['typus'], name='history_his_typus_c46ce5_idx'),
        ),
    ]
