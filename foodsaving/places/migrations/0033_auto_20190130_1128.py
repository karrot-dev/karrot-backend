# Generated by Django 2.1.5 on 2019-01-30 11:28
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.management import create_contenttypes
from django.db import migrations
from django.utils import timezone


def add_place_subscriptions(apps, schema_editor):
    """Adds place subscribers
    Only adds users who signed up for pickups one week ago or later
    """
    app_config = apps.get_app_config('places')
    app_config.models_module = app_config.models_module or True
    create_contenttypes(app_config)

    User = apps.get_model('users', 'User')
    Place = apps.get_model('places', 'Place')
    PlaceSubscription = apps.get_model('places', 'PlaceSubscription')
    Conversation = apps.get_model('conversations', 'Conversation')
    ConversationParticipant = apps.get_model('conversations', 'ConversationParticipant')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ct = ContentType.objects.get(app_label='places', model='place')

    for place in Place.objects.all():
        conversation, _ = Conversation.objects.get_or_create(target_type=ct, target_id=place.id)
        one_week_ago = timezone.now() - relativedelta(days=7)
        recent_collectors = User.objects.filter(
            pickup_dates__date__startswith__gte=one_week_ago,
            pickup_dates__place_id=place.id,
        ).distinct()
        for user in recent_collectors:
            PlaceSubscription.objects.create(user=user, place=place)
            ConversationParticipant.objects.create(user=user, conversation=conversation)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0021_user_email_deletable'),
        ('places', '0032_auto_20190130_1128'),
        ('pickups', '0013_auto_20190122_1210'),
        ('conversations', '0026_conversationmeta'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [migrations.RunPython(add_place_subscriptions, migrations.RunPython.noop, elidable=True)]
