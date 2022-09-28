# Generated by Django 3.2.15 on 2022-09-28 20:27

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0049_group_roles'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='group',
            name='roles',
        ),
        migrations.CreateModel(
            name='CustomRole',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('name', models.TextField()),
                ('description', models.TextField()),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='custom_roles', to='groups.group')),
            ],
            options={
                'unique_together': {('name', 'group')},
            },
        ),
    ]