
from django.db import migrations, models

def copy_threads_marked_at_from_conversation(apps, schema_editor):
    ConversationMeta = apps.get_model('conversations', 'ConversationMeta')
    ConversationMeta.objects.update(threads_marked_at=models.F('conversations_marked_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0033_conversationmeta_threads_marked_at'),
    ]

    operations = [
        migrations.RunPython(copy_threads_marked_at_from_conversation, migrations.RunPython.noop, elidable=True)
    ]
