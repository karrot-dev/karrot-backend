from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('conversations', '0002_auto_20160721_1447'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel('ConversationMessage'),
        migrations.DeleteModel('Conversation'),
    ]
