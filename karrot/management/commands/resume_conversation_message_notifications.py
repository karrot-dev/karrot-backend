from django.core.management.base import BaseCommand
from django.db.models import Q

from karrot.conversations import tasks
from karrot.conversations.models import ConversationMessage


class Command(BaseCommand):
    """
    Run this after redis was cleared or huey crashed.
    It'll make sure that outstanding email notifications about conversation messages will get sent.
    """
    def handle(self, *args, **options):
        # get all latest messages
        messages = ConversationMessage.objects.exclude(
            Q(conversation_latest_message=None) & Q(thread_latest_message=None)
        )
        for message in messages:
            tasks.notify_participants.schedule(args=(message, ), delay=5 * 60)
