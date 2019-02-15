from factory import DjangoModelFactory, CREATE_STRATEGY, post_generation

from karrot.conversations.models import Conversation


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
