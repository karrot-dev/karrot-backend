from channels.db import database_sync_to_async
from factory import DjangoModelFactory, CREATE_STRATEGY, post_generation

from foodsaving.conversations.models import Conversation


class ConversationFactory(DjangoModelFactory):
    class Meta:
        model = Conversation
        strategy = CREATE_STRATEGY

    @post_generation
    def participants(self, created, participants, **kwargs):
        if not created:
            return
        if participants:
            for user in participants:
                self.join(user)


# Note: the conversations returned have no special async wrappers, you would still need to wrap each method
# e.g. await database_sync_to_async(conversation.join)(user)
AsyncConversationFactory = database_sync_to_async(ConversationFactory)
