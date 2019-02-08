# Generated by Django 2.1.5 on 2019-01-30 11:28

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('places', '0031_auto_20181216_2133'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlaceSubscription',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
        migrations.AlterField(
            model_name='place',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='places', to='groups.Group'),
        ),
        migrations.AddField(
            model_name='placesubscription',
            name='place',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='places.Place'),
        ),
        migrations.AddField(
            model_name='placesubscription',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='place',
            name='subscribers',
            field=models.ManyToManyField(related_name='places_subscribed', through='places.PlaceSubscription', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(
            name='placesubscription',
            unique_together={('place', 'user')},
        ),
    ]
