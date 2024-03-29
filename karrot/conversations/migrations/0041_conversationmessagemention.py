# Generated by Django 3.2.10 on 2022-01-01 19:35

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conversations', '0040_conversationmessageimage'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConversationMessageMention',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='conversations.conversationmessage')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
