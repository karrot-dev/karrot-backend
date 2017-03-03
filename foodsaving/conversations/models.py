from enumfields import EnumField, Enum
from config import settings
from foodsaving.base.base_models import BaseModel
from django.db import models


class ConversationType(Enum):
    ONE_ON_ONE = 0
    MULTICHAT = 1


class Conversation(BaseModel):
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL)
    type = EnumField(ConversationType, default=ConversationType.ONE_ON_ONE)

    topic = models.TextField(null=True)


class ConversationMessage(BaseModel):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    in_conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)

    content = models.TextField()
