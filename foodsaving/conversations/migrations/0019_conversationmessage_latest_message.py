# Generated by Django 2.1 on 2018-08-23 19:38

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F


def set_latest_message(apps, schema_editor):
    ConversationMessage = apps.get_model('conversations', 'ConversationMessage')

    for thread in ConversationMessage.objects.filter(id=F('thread_id')):
        try:
            thread.latest_message = thread.thread_messages.latest('id')
            thread.save()
        except ConversationMessage.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0018_conversation_latest_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationmessage',
            name='latest_message',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='thread_latest_message',
                to='conversations.ConversationMessage'
            ),
        ),
        migrations.RunPython(set_latest_message, migrations.RunPython.noop, elidable=True)
    ]
