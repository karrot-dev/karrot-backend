from django.db import migrations, IntegrityError

from karrot.conversations import emoji_db


def convert_message_reactions(apps, schema_editor):
    Reaction = apps.get_model('conversations', 'ConversationMessageReaction')

    to_delete = []
    for reaction in Reaction.objects.exclude(name__in=emoji_db.emoji.keys()):
        if reaction.name in emoji_db.aliases:
            # rename
            new_name = emoji_db.aliases[reaction.name]
            if Reaction.objects.filter(message=reaction.message, user=reaction.user, name=new_name).exists():
                # would be duplicate after renaming
                to_delete.append(reaction.id)
            else:
                reaction.name = new_name
                reaction.save()
        else:
            to_delete.append(reaction.id)

    Reaction.objects.filter(id__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0030_set_is_group_public'),
    ]

    operations = [migrations.RunPython(convert_message_reactions, migrations.RunPython.noop, elidable=True)]
