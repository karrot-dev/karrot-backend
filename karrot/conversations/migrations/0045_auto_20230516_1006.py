# Generated by Django 3.2.15 on 2023-05-16 10:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0044_conversationmessageattachment_filename'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationmessageattachment',
            name='file_preview',
            field=models.ImageField(null=True, upload_to='conversation_message_attachment_preview'),
        ),
        migrations.AddField(
            model_name='conversationmessageattachment',
            name='file_thumbnail',
            field=models.ImageField(null=True, upload_to='conversation_message_attachment_thumbnail'),
        ),
    ]
