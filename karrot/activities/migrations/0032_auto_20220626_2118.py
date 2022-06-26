# Generated by Django 3.2.13 on 2022-06-26 21:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0031_activity_activities__date_5ffa2e_gist'),
    ]

    operations = [
        migrations.CreateModel(
            name='ICSAuthToken',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('token', models.TextField()),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='icsauthtoken',
            index=models.Index(fields=['token'], name='activities__token_21dcec_idx'),
        ),
    ]
