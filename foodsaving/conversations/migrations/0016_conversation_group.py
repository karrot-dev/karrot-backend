# Generated by Django 2.1 on 2018-08-22 18:07

from django.db import migrations, models
import django.db.models.deletion


def set_conversation_group(apps, schema_editor):
    Conversation = apps.get_model('conversations', 'Conversation')
    for c in Conversation.objects.exclude(target_id=None):
        c.group = c.target.group
        c.save()


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0032_groupmembership_added_by'),
        ('conversations', '0015_auto_20180728_1501'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='group',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='groups.Group'),
        ),
        migrations.RunPython(set_conversation_group, migrations.RunPython.noop, elidable=True)
    ]
