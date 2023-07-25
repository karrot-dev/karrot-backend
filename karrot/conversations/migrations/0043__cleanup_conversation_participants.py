from datetime import timedelta

from django.db import migrations
from django.db.models import Func, F

from karrot.conversations.models import ConversationParticipant


def cleanup_conversation_participants(apps, schema_editor):
    ConversationParticipant = apps.get_model('conversations', 'ConversationParticipant')
    ConversationThreadParticipant = apps.get_model('conversations', 'ConversationThreadParticipant')
    ConversationParticipant.objects.filter(conversation__group__isnull=False).exclude(conversation__group__members=F('user')).delete()
    ConversationThreadParticipant.objects.filter(thread__conversation__group__isnull=False).exclude(thread__conversation__group__members=F('user')).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('conversations', '0042_conversationmessageattachment'),
    ]

    operations = [
        migrations.RunPython(cleanup_conversation_participants, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
